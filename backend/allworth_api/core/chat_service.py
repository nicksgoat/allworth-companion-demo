# Streaming chat: vendor-agnostic LLM tool-use loop yielding (event, data)
# tuples.
import asyncio
import json
import logging
import re
import sys
import time
from collections.abc import AsyncIterator

from allworth_api.config import (
    llm_chat_max_tokens,
    llm_extract_max_tokens,
    llm_max_retries,
    llm_timeout_seconds,
)
from allworth_api.core.audit import estimate_tokens
from allworth_api.core.conversation_memory import append_turn, default_conversation_id, recent_messages
from allworth_api.core.memory import (
    active_facts,
    add_facts,
    append_episode,
    episodes_for,
    profile_as_context,
)
from allworth_api.core.nudges import nudges_for
from allworth_api.core.observability import hash_household_id
from allworth_api.core.prompts import STABLE_SYSTEM, volatile_context
from allworth_api.core.tool_defs import TOOL_DEFINITIONS, TOOL_LABELS
from allworth_api.core.tool_runner import run_tool
from allworth_api.core.vision_scorecard import score_chat_turn
from allworth_api.data.advisors import advisor_for_client
from allworth_api.data.llm import CHAT_MODEL, EXTRACT_MODEL, provider
from allworth_api.data.seed import seed

MAX_TOOL_ROUNDS = 8
logger = logging.getLogger("allworth_api.chat")

SOURCE_NAMES = {
    "get_client_context": "Client context",
    "get_portfolio_analytics": "Portfolio analytics",
    "run_monte_carlo": "Monte Carlo simulation",
    "run_mock_rebalance": "Mock rebalance",
    "get_document": "Planning documents",
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
LEGACY_ADVISOR_NAMES = ("Dana Whitfield", "Dana")


def reset_conversations() -> None:
    return None


def _advisor_first_name(advisor_name: str | None) -> str:
    return (advisor_name or "your advisor").split()[0]


def _sanitize_advisor_references(text: str, advisor_name: str | None) -> str:
    if not text:
        return text
    advisor_first = _advisor_first_name(advisor_name)
    cleaned = text
    for stale_name in LEGACY_ADVISOR_NAMES:
        cleaned = re.sub(rf"\b{re.escape(stale_name)}\b", advisor_first, cleaned)
    return cleaned


def _sanitize_messages(messages: list[dict], advisor_name: str | None) -> list[dict]:
    sanitized = []
    for message in messages:
        copied = dict(message)
        content = copied.get("content")
        if isinstance(content, str):
            copied["content"] = _sanitize_advisor_references(content, advisor_name)
        sanitized.append(copied)
    return sanitized


def _ensure_advisor_handoff(text: str, advisor_name: str | None) -> tuple[str, str]:
    if not text.strip() or not advisor_name:
        return text, ""
    advisor_first = _advisor_first_name(advisor_name)
    if re.search(rf"\b{re.escape(advisor_first)}\b", text, flags=re.IGNORECASE):
        return text, ""
    if re.search(r"\badvisor\b", text, flags=re.IGNORECASE):
        return text, ""
    suffix = (
        f"\n\nThis is worth pressure-testing with {advisor_first}, especially before treating it "
        "as a planning decision."
    )
    return text + suffix, suffix


def _core_suggestions(advisor_name: str | None = None) -> list[str]:
    advisor_first = _advisor_first_name(advisor_name)
    return [
        "What should we look at first?",
        "What changed since my last review?",
        f"What deserves {advisor_first}'s attention?",
    ]


def suggested_for(session: str, client_id: str | None = None) -> list[str]:
    candidates: list[str] = []
    advisor_name = advisor_for_client(client_id)["name"] if client_id else None
    if client_id:
        candidates.extend(_suggestions_from_nudges(client_id))
        candidates.extend(_suggestions_from_profile(client_id))
    if session == "wednesday":
        candidates.append("What changed since our last conversation?")
    candidates.extend(_core_suggestions(advisor_name))
    return _top_suggestions(candidates)


def _target_mix(message: str) -> str:
    match = re.search(r"\b(\d{2})\s*/\s*(\d{2})\b", message)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return "that target"


def _mentions_affordability(message: str) -> bool:
    text = message.lower()
    purchase_terms = (
        "afford",
        "buy",
        "purchase",
        "car",
        "vehicle",
        "auto",
        "truck",
        "house",
        "home",
        "mortgage",
        "boat",
        "vacation",
    )
    return any(term in text for term in purchase_terms)


def _mentions_retirement(message: str) -> bool:
    text = message.lower()
    retirement_terms = (
        "retire",
        "retirement",
        "on track",
        "run out",
        "money last",
        "income plan",
        "sustainable",
    )
    return any(term in text for term in retirement_terms)


def _mentions_rebalance(message: str) -> bool:
    text = message.lower()
    rebalance_terms = (
        "rebalance",
        "rebalancing",
        "allocation",
        "70/30",
        "60/40",
        "target",
        "model",
        "drift",
    )
    return any(term in text for term in rebalance_terms)


def _mentions_tax(message: str) -> bool:
    text = message.lower()
    return any(term in text for term in ("tax", "gain", "capital gain", "cost basis", "realized"))


def _mentions_spending(message: str) -> bool:
    text = message.lower()
    return any(term in text for term in ("spending", "budget", "expenses", "cash flow", "over plan"))


def _mentions_goal(message: str) -> bool:
    text = message.lower()
    return any(term in text for term in ("goal", "lake house", "529", "college", "timeline"))


def _suggestions_from_nudges(client_id: str) -> list[str]:
    suggestions = []
    for nudge in nudges_for(client_id):
        if nudge["type"] == "spending":
            suggestions.append("How does this spending affect my plan?")
        elif nudge["type"] == "concentration":
            title = nudge.get("title", "")
            symbol = title.split(" ", 1)[0] if title else "that position"
            suggestions.append(f"What are my options for {symbol}?")
    return suggestions


def _suggestions_from_profile(client_id: str) -> list[str]:
    suggestions = []
    for fact in active_facts(client_id):
        text = fact.get("fact", "").lower()
        category = fact.get("category")
        if category == "goals" and "lake house" in text:
            suggestions.append("Is the lake house goal still on track?")
        elif category == "goals" and "529" in text:
            suggestions.append("Are the 529 plans still funded?")
        elif category == "liquidity_events":
            suggestions.append("How does this liquidity decision affect my plan?")
        elif "tax" in text or "apple" in text:
            suggestions.append("How can we reduce the tax impact?")
        elif "plain-english" in text or "plain english" in text:
            suggestions.append("Explain the trade-offs in plain English")
    return suggestions


def _suggestions_from_answer(answer: str, advisor_name: str | None = None) -> list[str]:
    text = answer.lower()
    suggestions = []
    advisor_first = _advisor_first_name(advisor_name)
    if "advisor" in text or advisor_first.lower() in text:
        suggestions.append(f"What should I ask {advisor_first}?")
    if "tax" in text or "capital-gains" in text or "capital gains" in text:
        suggestions.append("Show the tax impact in plain English")
    if "downside" in text or "p10" in text or "weaker" in text:
        suggestions.append("How bad is the downside case?")
    if "rebalance" in text or "allocation" in text:
        suggestions.append("Which holdings would be sold first?")
    if "spending" in text or "budget" in text:
        suggestions.append("What spending level fits the plan?")
    return suggestions


def _top_suggestions(candidates: list[str], *, limit: int = 3) -> list[str]:
    seen = set()
    chosen = []
    for candidate in candidates:
        text = " ".join((candidate or "").split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        chosen.append(text)
        if len(chosen) >= limit:
            break
    return chosen


def contextual_suggestions(
    sources: set[str],
    session: str,
    message: str = "",
    answer: str = "",
    client_id: str | None = None,
) -> list[str]:
    candidates: list[str] = []
    advisor_name = advisor_for_client(client_id)["name"] if client_id else None
    advisor_first = _advisor_first_name(advisor_name)
    if _mentions_rebalance(message):
        mix = _target_mix(message)
        candidates.extend([
            f"Show the tax impact of moving to {mix}",
            "Which holdings would be sold first?",
            "What if we limit realized gains?",
        ])
    if _mentions_affordability(message):
        candidates.extend([
            "How would paying cash affect retirement odds?",
            "Which funding source creates the least tax drag?",
            "What monthly payment would still fit the plan?",
        ])
    if _mentions_retirement(message):
        candidates.extend([
            "What improves my odds the most?",
            "What if I retire one year later?",
            "How bad is the downside case?",
        ])
    if _mentions_tax(message):
        candidates.extend([
            "Which option creates the least tax drag?",
            "What if we cap realized gains?",
            f"What should {advisor_first} review before any sale?",
        ])
    if _mentions_spending(message):
        candidates.extend([
            "What spending level keeps the plan on track?",
            "Which categories are driving the overage?",
            "How does this affect the lake house timeline?",
        ])
    if _mentions_goal(message):
        candidates.extend([
            "What is the biggest risk to this goal?",
            "How much should I set aside monthly?",
            f"What should I ask {advisor_first} about this goal?",
        ])
    if "Mock rebalance" in sources or "Portfolio analytics" in sources or "Rebalance analysis" in sources:
        candidates.extend([
            "Show me the tax impact in plain English",
            f"What would {advisor_first} need to review?",
            "What happens if we wait a quarter?",
        ])
    if "Monte Carlo simulation" in sources:
        candidates.extend([
            "What improves the odds the most?",
            "What if I retire one year later?",
            "How bad is the downside case?",
        ])
    if "Planning documents" in sources:
        candidates.extend([
            "What goals matter most here?",
            f"What should I ask {advisor_first}?",
            "What changed since the last review?",
        ])
    candidates.extend(_suggestions_from_answer(answer, advisor_name))
    if client_id:
        candidates.extend(_suggestions_from_nudges(client_id))
        candidates.extend(_suggestions_from_profile(client_id))
    candidates.extend(suggested_for(session, client_id))
    return _top_suggestions(candidates)


async def _stream_live(
    client_id,
    session,
    messages,
    out,
    client_name=None,
    advisor_name=None,
    memory_used=False,
):
    turn_started = time.perf_counter()
    system = [
        {"type": "text", "text": STABLE_SYSTEM, "cache_control": {"type": "ephemeral"}},
        {
            "type": "text",
            "text": volatile_context(
                client_id,
                session,
                profile_as_context(client_id),
                _monday_recap(client_id, advisor_name) if session == "wednesday" else None,
                client_name=client_name,
                advisor_name=advisor_name,
            ),
        },
    ]

    convo = list(messages)
    sources = set()
    full_text = ""
    tool_count = 0
    tool_errors = 0
    tool_names: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        tool_calls = []
        async for event in _stream_provider_events(
            model=CHAT_MODEL,
            max_tokens=llm_chat_max_tokens(),
            system=system,
            tools=TOOL_DEFINITIONS,
            messages=convo,
        ):
            if event.type == "tool_use_start":
                name = event.data["name"]
                yield "tool_start", {"name": name, "label": TOOL_LABELS.get(name, name)}
            elif event.type == "text":
                delta = _sanitize_advisor_references(event.data["delta"], advisor_name)
                full_text += delta
                yield "text", {**event.data, "delta": delta}
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
            tool_count += 1
            tool_names.append(tc.name)
            if isinstance(result, dict) and "error" in result:
                tool_errors += 1
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

    final_sources = sorted(sources)
    full_text = _sanitize_advisor_references(full_text, advisor_name)
    full_text, advisor_suffix = _ensure_advisor_handoff(full_text, advisor_name)
    if advisor_suffix:
        yield "text", {"delta": advisor_suffix}
    latest_user_message = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    suggested = contextual_suggestions(sources, session, latest_user_message, full_text, client_id)
    quality = score_chat_turn(
        client_id=client_id,
        message=latest_user_message,
        answer=full_text,
        tool_calls=tool_names,
        sources=final_sources,
        suggestions=suggested,
        memory_used=memory_used,
    )
    yield "done", {
        "sources": final_sources,
        "suggested": suggested,
        "quality": {
            "vision_score": quality["vision_score"],
            "safety_flags": quality["safety_flags"],
            "missing": quality["missing"],
        },
    }
    out["text"] = full_text
    logger.info(
        json.dumps(
            {
                "event": "chat_turn",
                "client_hash": hash_household_id(client_id),
                "session": session,
                "provider": getattr(provider, "name", provider.__class__.__name__),
                "chat_model": CHAT_MODEL,
                "latency_ms": round((time.perf_counter() - turn_started) * 1000, 1),
                "tool_count": tool_count,
                "tool_expected": quality["tool_expected"],
                "tool_actual": quality["tool_actual"],
                "tool_errors": tool_errors,
                "sources": final_sources,
                "vision_score": quality["vision_score"],
                "safety_flags": quality["safety_flags"],
                "suggestion_score": quality["suggestion_score"],
                "memory_used": quality["memory_used"],
                "tokens_in_est": estimate_tokens(messages),
                "tokens_out_est": estimate_tokens(full_text),
            },
            separators=(",", ":"),
        )
    )


async def _stream_provider_events(**kwargs):
    attempts = llm_max_retries() + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        emitted = False
        try:
            async with asyncio.timeout(llm_timeout_seconds()):
                async for event in provider.stream_with_tools(**kwargs):
                    emitted = True
                    yield event
            return
        except Exception as err:
            last_error = err
            if emitted or attempt >= attempts - 1:
                raise
            await asyncio.sleep(0.25 * (attempt + 1))
    if last_error:
        raise last_error


async def stream_chat(
    client_id: str,
    session: str,
    message: str,
    conversation_id: str | None = None,
) -> AsyncIterator[tuple[str, dict]]:
    """Async generator of (event, data) tuples for one stateless chat turn."""
    client = next((c for c in seed["personas"]["clients"] if c["id"] == client_id), None)
    advisor = advisor_for_client(client_id)
    client_name = client["name"] if client else None
    advisor_name = advisor["name"]
    conversation_id = conversation_id or default_conversation_id(client_id, session)
    prior_messages = await recent_messages(client_id, conversation_id)
    messages = _sanitize_messages([
        *prior_messages,
        {"role": "user", "content": message},
    ], advisor_name)
    user_text = message
    out = {"text": ""}

    try:
        if not provider:
            yield "error", {"message": "The assistant is temporarily unavailable."}
            return
        else:
            try:
                async for chunk in _stream_live(
                    client_id,
                    session,
                    messages,
                    out,
                    client_name,
                    advisor_name,
                    memory_used=bool(prior_messages),
                ):
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
    sanitized_answer = _sanitize_advisor_references(out["text"], advisor_name)
    append_episode(client_id, session, "assistant", sanitized_answer)
    await append_turn(client_id, conversation_id, user_text, sanitized_answer)
    task = asyncio.create_task(_extract_facts(client_id, user_text))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _monday_recap(client_id, advisor_name: str | None = None):
    eps = episodes_for(client_id, "monday")
    if not eps:
        return None
    summary = "\n".join(e["content"] for e in eps if e["role"] == "assistant")
    return _sanitize_advisor_references(summary, advisor_name) or None


async def _extract_facts(client_id, user_text):
    if not provider or not user_text:
        return
    try:
        async with asyncio.timeout(llm_timeout_seconds()):
            result = await provider.complete(
                model=EXTRACT_MODEL,
                max_tokens=llm_extract_max_tokens(),
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
