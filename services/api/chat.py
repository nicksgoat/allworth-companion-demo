# Streaming chat: Anthropic tool-use loop over SSE, with cached fallback
# responses so the demo never dies on stage.
import asyncio
import json
import os
import re
import sys

from anthropic import AsyncAnthropic

from data import API_DIR
from memory import add_facts, append_episode, episodes_for, profile_as_context
from prompts import STABLE_SYSTEM, volatile_context
from tools import TOOL_DEFINITIONS, TOOL_LABELS, run_tool

CHAT_MODEL = "claude-opus-4-7"
EXTRACT_MODEL = "claude-haiku-4-5"
MAX_TOOL_ROUNDS = 8

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
client = AsyncAnthropic(api_key=api_key) if api_key else None

SOURCE_NAMES = {
    "get_accounts": "Accounts",
    "get_portfolio": "Portfolio",
    "get_financial_plan": "Financial plan",
    "get_spending": "Spending",
    "get_client_profile": "Your profile",
    "update_client_profile": "Your profile",
    "simulate_tax_impact": "Tax estimate",
    "get_advisor_brief": "Advisor brief",
}

# Conversation state per client+session, reset via demo control.
conversations: dict[str, list] = {}

_bg_tasks: set[asyncio.Task] = set()


def reset_conversations():
    conversations.clear()


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'), ensure_ascii=False)}\n\n"


def suggested_for(session):
    if session == "wednesday":
        return ["What changed since I was last here?", "Where did we land on the SpaceX IPO?"]
    return ["What would $200K into the SpaceX IPO mean for me?"]


def _load_fallback(name):
    return json.loads((API_DIR / "fallbacks" / f"{name}.json").read_text())


def _pick_fallback(user_text, session):
    text = user_text.lower()
    beat3 = _load_fallback("beat3")
    beat4 = _load_fallback("beat4")
    changed = _load_fallback("whats_changed")
    # Wednesday: "what changed?" beats the memory beat, which beats everything else.
    if session == "wednesday" and any(m in text for m in changed["match"]):
        return changed
    if session == "wednesday" and any(m in text for m in beat4["match"]):
        return beat4
    if any(m in text for m in beat3["match"]):
        return beat3
    return beat4 if session == "wednesday" else beat3


async def _stream_fallback(user_text, session, out):
    fb = _pick_fallback(user_text, session)
    for tool in fb["tools"]:
        yield sse("tool_start", {"name": tool, "label": TOOL_LABELS.get(tool, tool)})
        await asyncio.sleep(0.45)
        yield sse("tool_end", {"name": tool})
    # Stream the cached text in word chunks so it feels live.
    words = fb["text"].split(" ")
    for i in range(0, len(words), 6):
        yield sse("text", {"delta": " ".join(words[i : i + 6]) + " "})
        await asyncio.sleep(0.04)
    yield sse("done", {"sources": fb["sources"], "fallback": True, "suggested": fb.get("suggested", [])})
    out["text"] = fb["text"]


async def _stream_live(client_id, session, messages, out):
    system = [
        {"type": "text", "text": STABLE_SYSTEM, "cache_control": {"type": "ephemeral"}},
        {
            "type": "text",
            "text": volatile_context(
                client_id,
                session,
                profile_as_context(client_id),
                _monday_recap(client_id) if session == "wednesday" else None,
            ),
        },
    ]

    convo = list(messages)
    sources = set()
    full_text = ""

    for _ in range(MAX_TOOL_ROUNDS):
        async with client.messages.stream(
            model=CHAT_MODEL,
            max_tokens=2048,
            system=system,
            tools=TOOL_DEFINITIONS,
            messages=convo,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "tool_use":
                    name = event.content_block.name
                    yield sse("tool_start", {"name": name, "label": TOOL_LABELS.get(name, name)})
                elif event.type == "text":
                    full_text += event.text
                    yield sse("text", {"delta": event.text})
            response = await stream.get_final_message()

        convo.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = run_tool(block.name, block.input, client_id)
            sources.add(SOURCE_NAMES.get(block.name, block.name))
            yield sse("tool_end", {"name": block.name})
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )
        convo.append({"role": "user", "content": results})

    yield sse("done", {"sources": sorted(sources), "fallback": False, "suggested": suggested_for(session)})
    out["text"] = full_text


async def stream_chat(client_id, session, message):
    """Async generator of SSE strings for one chat turn. Owns conversation state."""
    key = f"{client_id}:{session}"
    history = conversations.get(key, [])
    messages = [*history, {"role": "user", "content": message}]
    user_text = _last_user_text(messages)
    out = {"text": ""}

    try:
        if not client:
            async for chunk in _stream_fallback(user_text, session, out):
                yield chunk
        else:
            try:
                async for chunk in _stream_live(client_id, session, messages, out):
                    yield chunk
            except Exception as err:
                print(f"[chat] live stream failed, using fallback: {err}", file=sys.stderr)
                yield sse("text", {"delta": "\n"})
                async for chunk in _stream_fallback(user_text, session, out):
                    yield chunk
    except Exception as err:
        print(f"[chat] unrecoverable: {err}", file=sys.stderr)
        yield sse("error", {"message": "Something went wrong. Please try again."})
        return

    conversations[key] = [*messages, {"role": "assistant", "content": out["text"]}]

    # Persist the turn and extract facts in the background (never blocks the response).
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


# Lightweight second-model pass: pull durable facts out of the client's message.
async def _extract_facts(client_id, user_text):
    if not client or not user_text:
        return
    try:
        response = await client.messages.create(
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
        text = "".join(b.text for b in response.content if b.type == "text")
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
