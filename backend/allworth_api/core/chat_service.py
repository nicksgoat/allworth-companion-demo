# Streaming chat: vendor-agnostic LLM tool-use loop yielding (event, data)
# tuples, with cached fallback responses so the demo never dies on stage.
import asyncio
import json
import re
import sys
from collections.abc import AsyncIterator

from allworth_api.core.auth import get_session_for_household
from allworth_api.core.memory import (
    add_facts,
    append_episode,
    episodes_for,
    profile_as_context,
)
from allworth_api.core.prompts import STABLE_SYSTEM, volatile_context
from allworth_api.core.tool_defs import TOOL_DEFINITIONS, TOOL_LABELS
from allworth_api.core.tool_runner import run_tool
from allworth_api.data.llm import CHAT_MODEL, EXTRACT_MODEL, provider
from allworth_api.data.fallbacks import pick_fallback
from allworth_api.data.seed import seed

MAX_TOOL_ROUNDS = 8

SOURCE_NAMES = {
    "get_accounts": "Accounts",
    "get_portfolio": "Portfolio",
    "get_financial_plan": "Financial plan",
    "get_spending": "Spending",
    "get_client_profile": "Your profile",
    "update_client_profile": "Your profile",
    "simulate_tax_impact": "Tax estimate",
    "get_advisor_brief": "Advisor brief",
    "run_retirement_projection": "Retirement model",
    "analyze_portfolio_drift": "Portfolio analysis",
    "run_roth_conversion_analysis": "Roth analysis",
    "analyze_goal_funding": "Goal tracker",
    "analyze_income_sustainability": "Income plan",
}

# Conversation state per client+session, reset via demo control.
conversations: dict[str, list] = {}

_bg_tasks: set[asyncio.Task] = set()


def reset_conversations() -> None:
    conversations.clear()


def suggested_for(session: str) -> list[str]:
    if session == "wednesday":
        return ["What changed since I was last here?", "Where did we land on the SpaceX IPO?"]
    return ["What would $200K into the SpaceX IPO mean for me?"]


async def _stream_fallback(user_text, session, out):
    fb = pick_fallback(user_text, session)
    for tool in fb["tools"]:
        yield "tool_start", {"name": tool, "label": TOOL_LABELS.get(tool, tool)}
        await asyncio.sleep(0.45)
        yield "tool_end", {"name": tool}
    words = fb["text"].split(" ")
    for i in range(0, len(words), 6):
        yield "text", {"delta": " ".join(words[i : i + 6]) + " "}
        await asyncio.sleep(0.04)
    yield "done", {"sources": fb["sources"], "fallback": True, "suggested": fb.get("suggested", [])}
    out["text"] = fb["text"]


async def _stream_live(client_id, session, messages, out, client_name=None, advisor_name=None):
    system = [
        {"type": "text", "text": STABLE_SYSTEM, "cache_control": {"type": "ephemeral"}},
        {
            "type": "text",
            "text": volatile_context(
                client_id,
                session,
                profile_as_context(client_id),
                _monday_recap(client_id) if session == "wednesday" else None,
                client_name=client_name,
                advisor_name=advisor_name,
            ),
        },
    ]

    convo = list(messages)
    sources = set()
    full_text = ""

    for _ in range(MAX_TOOL_ROUNDS):
        tool_calls = []
        async for event in provider.stream_with_tools(
            model=CHAT_MODEL,
            max_tokens=2048,
            system=system,
            tools=TOOL_DEFINITIONS,
            messages=convo,
        ):
            if event.type == "tool_use_start":
                name = event.data["name"]
                yield "tool_start", {"name": name, "label": TOOL_LABELS.get(name, name)}
            elif event.type == "text":
                full_text += event.data["delta"]
                yield "text", event.data
            elif event.type == "done":
                tool_calls = event.data.get("tool_calls", [])
                stop_reason = event.data.get("stop_reason", "end_turn")
                raw_content = event.data.get("raw_content")

        # Append assistant message to conversation
        if raw_content is not None:
            # Anthropic: raw content blocks include tool_use blocks
            convo.append({"role": "assistant", "content": raw_content})
        elif tool_calls:
            # OpenAI/Azure: must include tool_calls in assistant message
            assistant_msg: dict = {"role": "assistant"}
            if full_text:
                assistant_msg["content"] = full_text
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.input),
                    },
                }
                for tc in tool_calls
            ]
            convo.append(assistant_msg)
        else:
            convo.append({"role": "assistant", "content": full_text})

        if stop_reason != "tool_use" or not tool_calls:
            break

        # Execute tool calls and format results
        results = []
        for tc in tool_calls:
            result = run_tool(tc.name, tc.input, client_id)
            sources.add(SOURCE_NAMES.get(tc.name, tc.name))
            yield "tool_end", {"name": tc.name}
            results.append(json.dumps(result))

        # Format tool results in provider-specific way and add to conversation
        tool_result_msg = provider.format_tool_results(tool_calls, results)
        if isinstance(tool_result_msg, list):
            # OpenAI: multiple tool messages
            convo.extend(tool_result_msg)
        else:
            # Anthropic: single user message with tool_result blocks
            convo.append(tool_result_msg)

    yield "done", {"sources": sorted(sources), "fallback": False, "suggested": suggested_for(session)}
    out["text"] = full_text


async def stream_chat(client_id: str, session: str, message: str) -> AsyncIterator[tuple[str, dict]]:
    """Async generator of (event, data) tuples for one chat turn. Owns conversation state."""
    key = f"{client_id}:{session}"
    history = conversations.get(key, [])
    messages = [*history, {"role": "user", "content": message}]
    user_text = _last_user_text(messages)
    out = {"text": ""}

    # Resolve client/advisor names from the authenticated session
    auth_session = get_session_for_household(client_id)
    client_name = auth_session.contact_name if auth_session else None
    # Use seed advisor name as default (Synapse advisor assignment not yet available)
    advisor_name = seed["personas"]["advisors"][0]["name"]

    try:
        if not provider:
            async for chunk in _stream_fallback(user_text, session, out):
                yield chunk
        else:
            try:
                async for chunk in _stream_live(client_id, session, messages, out, client_name, advisor_name):
                    yield chunk
            except Exception as err:
                print(f"[chat] live stream failed, using fallback: {err}", file=sys.stderr)
                yield "text", {"delta": "\n"}
                async for chunk in _stream_fallback(user_text, session, out):
                    yield chunk
    except Exception as err:
        print(f"[chat] unrecoverable: {err}", file=sys.stderr)
        yield "error", {"message": "Something went wrong. Please try again."}
        return

    conversations[key] = [*messages, {"role": "assistant", "content": out["text"]}]

    append_episode(client_id, session, "user", user_text)
    append_episode(client_id, session, "assistant", out["text"])
    task = asyncio.create_task(_extract_facts(client_id, user_text))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _monday_recap(client_id):
    eps = episodes_for(client_id, "monday")
    if not eps:
        return None
    summary = "\n".join(e["content"] for e in eps if e["role"] == "assistant")
    return summary or None


def _last_user_text(messages):
    for m in reversed(messages):
        if m["role"] != "user":
            continue
        if isinstance(m["content"], str):
            return m["content"]
        text = " ".join(b["text"] for b in m["content"] if b.get("type") == "text")
        if text:
            return text
    return ""


async def _extract_facts(client_id, user_text):
    if not provider or not user_text:
        return
    try:
        result = await provider.complete(
            model=EXTRACT_MODEL,
            max_tokens=1024,
            system=(
                "Extract durable facts about the client from their message — goals, preferences, "
                "concerns, liquidity events, outside assets, life events. Only facts that matter "
                "months from now; skip questions and small talk. Respond with ONLY a JSON array "
                '(possibly empty): [{"fact": string, "category": "goals"|"preferences"|"concerns"|'
                '"liquidity_events"|"outside_assets_mentioned"|"life_events", "source_quote": string, '
                '"confidence": number}]'
            ),
            messages=[{"role": "user", "content": user_text}],
        )
        text = result.text
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return
        facts = json.loads(match.group(0))
        if isinstance(facts, list) and facts:
            added = add_facts(client_id, facts, None)
            if added:
                print(f"[memory] learned {len(added)} fact(s) about {client_id}", file=sys.stderr)
    except Exception as err:
        print(f"[extract] {err}", file=sys.stderr)
