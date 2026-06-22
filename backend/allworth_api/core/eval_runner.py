"""Deterministic LLM/product eval harness for the Allworth quality loop."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from allworth_api.config import API_DIR
from allworth_api.core.audit import estimate_tokens
from allworth_api.core.chat_service import stream_chat
from allworth_api.core.tool_runner import run_tool
from allworth_api.core.vision_scorecard import score_chat_turn

EVAL_CASES_PATH = Path(API_DIR) / "evals" / "vision_cases.json"
PASSING_SCORE = 80


def load_eval_cases(path: Path | None = None) -> list[dict[str, Any]]:
    case_path = path or EVAL_CASES_PATH
    return json.loads(case_path.read_text())


def run_eval_suite(path: Path | None = None) -> dict[str, Any]:
    cases = load_eval_cases(path)
    results = [_run_case(case) for case in cases]
    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    avg_score = round(sum(result["score"] for result in results) / max(len(results), 1), 1)
    return {
        "ok": failed == 0,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "average_score": avg_score,
        "results": results,
    }


async def run_live_eval_suite(
    *,
    path: Path | None = None,
    max_cases: int = 3,
    max_estimated_tokens: int = 8_000,
    timeout_seconds: float = 60.0,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run a small, budgeted live eval against the configured LLM provider.

    This is opt-in and intentionally bounded. Routine CI should use
    run_eval_suite(), which scores fixture answers without spending model tokens.
    """

    cases = select_eval_cases(load_eval_cases(path), case_ids=case_ids, max_cases=max_cases)
    results = []
    spent_estimate = 0
    skipped_estimate = 0
    skipped = 0
    for case in cases:
        estimated_case_cost = _estimate_live_case_tokens(case)
        if spent_estimate + estimated_case_cost > max_estimated_tokens:
            skipped += 1
            skipped_estimate += estimated_case_cost
            continue
        result = await _run_live_case(case, timeout_seconds=timeout_seconds)
        spent_estimate += max(estimated_case_cost, result["tokens_estimated"])
        results.append(result)

    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    avg_score = round(sum(result["score"] for result in results) / max(len(results), 1), 1)
    return {
        "ok": bool(results) and failed == 0,
        "mode": "live",
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "skipped_for_budget": skipped,
        "skipped_estimated_tokens": skipped_estimate,
        "average_score": avg_score,
        "estimated_tokens": spent_estimate,
        "max_estimated_tokens": max_estimated_tokens,
        "timeout_seconds": timeout_seconds,
        "results": results,
    }


def select_eval_cases(
    cases: list[dict[str, Any]],
    *,
    case_ids: list[str] | None = None,
    max_cases: int | None = None,
) -> list[dict[str, Any]]:
    if case_ids:
        requested = [case_id for case_id in case_ids if case_id]
        by_id = {case["id"]: case for case in cases}
        selected = [by_id[case_id] for case_id in requested if case_id in by_id]
    else:
        selected = cases
    if max_cases is not None:
        selected = selected[:max_cases]
    return selected


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    direct_tool_ok, direct_tool_error = _check_direct_tool(case)
    score = score_chat_turn(
        client_id=case.get("client_id", "maya"),
        message=case["message"],
        answer=case["answer"],
        tool_calls=case.get("tool_calls", []),
        sources=case.get("sources", []),
        suggestions=case.get("suggestions", []),
        expected_tools=case.get("expected_tools", []),
        expected_sources=case.get("expected_sources", []),
        required_phrases=case.get("required_phrases", []),
        forbidden_phrases=case.get("forbidden_phrases", []),
        required_model_names=case.get("required_model_names", []),
        require_advisor=case.get("require_advisor", True),
        memory_used=case.get("memory_used", False),
    )
    passed = score["vision_score"] >= case.get("min_score", PASSING_SCORE) and direct_tool_ok
    return {
        "id": case["id"],
        "title": case["title"],
        "passed": passed,
        "score": score["vision_score"],
        "missing": score["missing"],
        "safety_flags": score["safety_flags"],
        "experience_signals": score["experience_signals"],
        "memory_used": score["memory_used"],
        "suggestion_score": score["suggestion_score"],
        "tool_expected": score["tool_expected"],
        "tool_actual": score["tool_actual"],
        "direct_tool_ok": direct_tool_ok,
        "direct_tool_error": direct_tool_error,
    }


async def _run_live_case(case: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
    client_id = case.get("client_id", "maya")
    conversation_id = f"eval:{case['id']}:{uuid.uuid4().hex[:8]}"
    answer = ""
    tool_calls = []
    sources = []
    suggestions = []
    error = None
    try:
        async with asyncio.timeout(timeout_seconds):
            async for event, data in stream_chat(
                client_id,
                case.get("session", "wednesday"),
                case["message"],
                conversation_id,
            ):
                if event == "tool_start":
                    tool_calls.append(data.get("name", ""))
                elif event == "text":
                    answer += data.get("delta", "")
                elif event == "done":
                    sources = data.get("sources", [])
                    suggestions = data.get("suggested", [])
                elif event == "error":
                    error = data.get("message", "unknown live eval error")
                    break
    except TimeoutError:
        error = f"live eval timed out after {timeout_seconds:.1f}s"

    score = score_chat_turn(
        client_id=client_id,
        message=case["message"],
        answer=answer,
        tool_calls=tool_calls,
        sources=sources,
        suggestions=suggestions,
        expected_tools=case.get("expected_tools", []),
        expected_sources=case.get("expected_sources", []),
        required_phrases=case.get("required_phrases", []),
        forbidden_phrases=case.get("forbidden_phrases", []),
        required_model_names=case.get("required_model_names", []),
        require_advisor=case.get("require_advisor", True),
        memory_used=case.get("memory_used", False),
    )
    passed = error is None and score["vision_score"] >= case.get("min_score", PASSING_SCORE)
    return {
        "id": case["id"],
        "title": case["title"],
        "passed": passed,
        "score": score["vision_score"],
        "missing": score["missing"],
        "safety_flags": score["safety_flags"],
        "experience_signals": score["experience_signals"],
        "memory_used": score["memory_used"],
        "suggestion_score": score["suggestion_score"],
        "tool_expected": score["tool_expected"],
        "tool_actual": tool_calls,
        "sources": sources,
        "suggestions": suggestions,
        "answer_preview": answer[:600],
        "tokens_estimated": estimate_tokens([case["message"], answer]),
        "error": error,
    }


def _estimate_live_case_tokens(case: dict[str, Any]) -> int:
    # Conservative pre-flight estimate: prompt + expected answer budget + tool chatter.
    return estimate_tokens(case.get("message", "")) + estimate_tokens(case.get("answer", "")) + 1_000


def _check_direct_tool(case: dict[str, Any]) -> tuple[bool, str | None]:
    check = case.get("direct_tool")
    if not check:
        return True, None
    result = run_tool(check["name"], check.get("input", {}), case.get("client_id", "maya"))
    if "error" in result:
        return False, str(result["error"])
    for required_key in check.get("required_keys", []):
        if not _has_path(result, required_key):
            return False, f"missing tool result key: {required_key}"
    for contains in check.get("contains", []):
        haystack = json.dumps(result, sort_keys=True)
        if contains not in haystack:
            return False, f"tool result did not contain: {contains}"
    return True, None


def _has_path(value: dict[str, Any], path: str) -> bool:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True
