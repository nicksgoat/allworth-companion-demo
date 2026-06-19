# Streaming chat: vendor-agnostic LLM tool-use loop yielding (event, data)
# tuples.
import asyncio
import json
import re
import sys
from collections.abc import AsyncIterator

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
from allworth_api.data.seed import seed

MAX_TOOL_ROUNDS = 8

SOURCE_NAMES = {
    "get_accounts": "Accounts",
    "get_portfolio": "Portfolio",
    "simulate": "Monte Carlo simulation",
    "rebalance": "Rebalance analysis",
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

_bg_tasks: set[asyncio.Task] = set()


def reset_conversations() -> None:
    return None


def suggested_for(session: str) -> list[str]:
    if session == "wednesday":
        return [
            "Am I on track for retirement?",
            "Can I afford a $50,000 car?",
            "What would rebalancing to 70/30 look like?",
        ]
    return [
        "Am I on track for retirement?",
        "Can I save for a house in 5 years?",
        "What would a $300,000 mortgage payment be?",
    ]


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

    yield "done", {"sources": sorted(sources), "suggested": suggested_for(session)}
    out["text"] = full_text


async def stream_chat(client_id: str, session: str, message: str) -> AsyncIterator[tuple[str, dict]]:
    """Async generator of (event, data) tuples for one stateless chat turn."""
    messages = [{"role": "user", "content": message}]
    user_text = message
    out = {"text": ""}

    client = next((c for c in seed["personas"]["clients"] if c["id"] == client_id), None)
    advisor = seed["personas"]["advisors"][0]
    client_name = client["name"] if client else None
    advisor_name = advisor["name"]

    try:
        if not provider:
            yield "error", {"message": "The assistant is temporarily unavailable."}
            return
        else:
            try:
                async for chunk in _stream_live(client_id, session, messages, out, client_name, advisor_name):
                    yield chunk
            except Exception as err:
                print(f"[chat] live stream failed: {err}", file=sys.stderr)
                yield "error", {"message": "The assistant is temporarily unavailable."}
                return
    except Exception as err:
        print(f"[chat] unrecoverable: {err}", file=sys.stderr)
        yield "error", {"message": "Something went wrong. Please try again."}
        return

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
