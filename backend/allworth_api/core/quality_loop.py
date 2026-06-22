"""Quality-loop reporting for production readiness and app vision alignment."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from typing import Any

from allworth_api import mcp as mcp_module
from allworth_api.config import API_DIR
from allworth_api.core.eval_runner import run_eval_suite
from allworth_api.core.feedback import feedback_log_path
from allworth_api.core.formatting import iso_now
from allworth_api.core.system_status import readiness_status
from allworth_api.core.vision_scorecard import LEGACY_STATIC_SUGGESTIONS, score_chat_turn
from allworth_api.financial_tools.tools import run_financial_tool
from allworth_api.routes.clients import dashboard


def build_quality_report(live_evals: dict[str, Any] | None = None) -> dict[str, Any]:
    readiness = readiness_status()
    evals = run_eval_suite()
    mcp = run_mcp_smoke()
    performance = run_performance_smoke()
    frontend_static = run_frontend_static_smoke()
    feedback = summarize_feedback()
    review_items = build_review_items(feedback["entries"])
    gates = {
        "readiness": readiness["ok"],
        "evals": evals["ok"],
        "mcp": mcp["ok"],
        "performance": performance["ok"],
        "frontend_static": frontend_static["ok"],
        "live_evals": True if live_evals is None else live_evals["ok"],
        "negative_feedback_reviewed": feedback["negative"] == 0 or bool(review_items),
    }
    ok = all(gates.values())
    return {
        "generated_at": iso_now(),
        "ok": ok,
        "release_recommendation": "PASS" if ok else "BLOCK",
        "gates": gates,
        "readiness": readiness,
        "evals": evals,
        "mcp": mcp,
        "performance": performance,
        "frontend_static": frontend_static,
        "live_evals": live_evals,
        "feedback": {k: v for k, v in feedback.items() if k != "entries"},
        "experience_metrics": experience_metrics(evals),
        "review_items": review_items,
        "draft_eval_fixtures": draft_eval_fixtures(review_items, feedback["entries"]),
        "top_gaps": top_gaps(evals, review_items, readiness, mcp, performance, frontend_static),
        "proposed_improvements": proposed_improvements(
            evals, review_items, live_evals, readiness, mcp, performance, frontend_static
        ),
        "next_best_action": next_best_action(
            evals, review_items, live_evals, readiness, mcp, performance, frontend_static
        ),
    }


def summarize_feedback(path: Path | None = None) -> dict[str, Any]:
    feedback_path = path or feedback_log_path()
    entries = []
    if feedback_path.exists():
        for line in feedback_path.read_text().splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    ratings = Counter(entry.get("rating") for entry in entries)
    return {
        "total": len(entries),
        "positive": ratings.get("positive", 0),
        "negative": ratings.get("negative", 0),
        "entries": entries,
    }


def run_mcp_smoke() -> dict[str, Any]:
    errors = []
    try:
        tools = asyncio.run(mcp_module.list_tools())
        tool_names = {tool.name for tool in tools}
        for required in ("simulate", "rebalance"):
            if required not in tool_names:
                errors.append(f"missing MCP tool: {required}")
        for forbidden in ("update_client_profile", "compare_scenarios"):
            if forbidden in tool_names:
                errors.append(f"mutable or unsupported MCP tool exposed: {forbidden}")

        denied = asyncio.run(mcp_module.call_tool("update_client_profile", {"fact": "test"}))
        if not denied.isError:
            errors.append("mutation tool was not rejected")
        elif "read-only boundary" not in denied.content[0].text:
            errors.append("mutation rejection did not mention read-only boundary")

        result = asyncio.run(mcp_module.call_tool("get_accounts", {}))
        if result.isError:
            errors.append("get_accounts returned an MCP error")
        else:
            envelope = json.loads(result.content[0].text)
            if envelope.get("source") != mcp_module.SOURCE:
                errors.append("MCP envelope missing source")
            if envelope.get("read_only") is not True:
                errors.append("MCP envelope missing read_only=true")
            if "netWorth" not in envelope.get("data", {}):
                errors.append("MCP get_accounts payload missing netWorth")
    except Exception as err:
        errors.append(f"MCP smoke failed: {err}")

    return {
        "ok": not errors,
        "tool_count": len(tool_names) if "tool_names" in locals() else 0,
        "errors": errors,
    }


def run_performance_smoke() -> dict[str, Any]:
    """Exercise hot non-LLM paths with bounded local concurrency."""

    scenarios = [
        (
            "dashboard",
            lambda: dashboard("maya", "maya"),
            {"iterations": 40, "workers": 8, "p95_budget_ms": 500.0},
        ),
        (
            "simulate",
            lambda: run_financial_tool(
                "simulate",
                {
                    "initial_value": 2_500_000,
                    "annual_contribution": -120_000,
                    "years": 20,
                    "n_simulations": 2_000,
                    "goal_amount": 1_000_000,
                },
                "maya",
            ),
            {"iterations": 16, "workers": 4, "p95_budget_ms": 1_500.0},
        ),
        (
            "rebalance",
            lambda: run_financial_tool(
                "rebalance",
                {
                    "model_id": "AWF - Core-Satellite - 70/30",
                    "tax_budget": {
                        "max_tax": 10_000,
                        "long_term_rate": 0.188,
                        "short_term_rate": 0.35,
                    },
                },
                "maya",
            ),
            {"iterations": 24, "workers": 6, "p95_budget_ms": 500.0},
        ),
    ]
    results = []
    errors = []
    for name, fn, config in scenarios:
        measurements: list[float] = []

        def timed_call(fn=fn) -> float:
            start = perf_counter()
            result = fn()
            if isinstance(result, dict) and result.get("error"):
                raise RuntimeError(str(result["error"]))
            return (perf_counter() - start) * 1000

        try:
            with ThreadPoolExecutor(max_workers=config["workers"]) as executor:
                measurements = list(executor.map(lambda _: timed_call(), range(config["iterations"])))
        except Exception as err:
            errors.append(f"{name}: {err}")
            measurements = []

        p95 = percentile(measurements, 95)
        passed = bool(measurements) and p95 <= config["p95_budget_ms"]
        if not passed:
            errors.append(
                f"{name}: p95 {round(p95, 2)}ms exceeded {config['p95_budget_ms']}ms budget"
            )
        results.append(
            {
                "name": name,
                "iterations": config["iterations"],
                "workers": config["workers"],
                "p50_ms": round(percentile(measurements, 50), 2),
                "p95_ms": round(p95, 2),
                "budget_ms": config["p95_budget_ms"],
                "passed": passed,
            }
        )
    return {"ok": not errors, "results": results, "errors": errors}


def run_frontend_static_smoke() -> dict[str, Any]:
    """Catch UX copy that implies a real advisor action happened when it did not."""

    repo_root = Path(API_DIR).parent
    checks = [
        {
            "path": repo_root / "frontend" / "src" / "components" / "AdvisorHandoffCard.tsx",
            "forbidden": [
                "Flagged for your next session",
                "Message sent",
                "Meeting scheduled",
                "Sent to",
                "Scheduled with",
            ],
        }
    ]
    errors = []
    for check in checks:
        path = check["path"]
        if not path.exists():
            errors.append(f"missing frontend file: {path.relative_to(repo_root)}")
            continue
        text = path.read_text()
        for phrase in check["forbidden"]:
            if phrase in text:
                errors.append(
                    f"{path.relative_to(repo_root)} contains delivery-implying copy: {phrase}"
                )
    return {"ok": not errors, "checked_files": len(checks), "errors": errors}


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = max(min(round((pct / 100) * (len(sorted_values) - 1)), len(sorted_values) - 1), 0)
    return sorted_values[index]


def build_review_items(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for entry in entries:
        rating = entry.get("rating")
        sources = entry.get("sources", [])
        tool_calls = entry.get("tool_calls_used", [])
        suggestions = entry.get("suggestions", [])
        quality = entry.get("quality") or {}
        quality_missing = quality.get("missing") or []
        safety_flags = quality.get("safety_flags") or []
        vision_score = quality.get("vision_score")
        reasons = []
        if rating == "negative":
            reasons.append("negative_feedback")
        if not sources:
            reasons.append("missing_sources")
        if not tool_calls:
            reasons.append("missing_tool_calls")
        if set(suggestions) == LEGACY_STATIC_SUGGESTIONS:
            reasons.append("static_suggestions")
        if isinstance(vision_score, int | float) and vision_score < 80:
            reasons.append("low_vision_score")
        reasons.extend(f"missing:{item}" for item in quality_missing)
        reasons.extend(f"safety:{item}" for item in safety_flags)
        if reasons:
            items.append(
                {
                    "conversation_id": entry.get("conversation_id", ""),
                    "message_id": entry.get("message_id", ""),
                    "answer_preview": entry.get("answer_preview", ""),
                    "reasons": reasons,
                    "category": classify_review_item(reasons),
                }
            )
    return items[-25:]


def score_review_candidate(*, client_id: str, message: str, answer: str, **kwargs: Any) -> dict[str, Any]:
    """Helper for turning repeated review items into future eval fixtures."""

    return score_chat_turn(client_id=client_id, message=message, answer=answer, **kwargs)


def draft_eval_fixtures(
    review_items: list[dict[str, Any]],
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn feedback/review items into human-reviewable eval fixture drafts."""

    by_message = {entry.get("message_id", ""): entry for entry in entries}
    drafts = []
    for item in review_items[-10:]:
        entry = by_message.get(item["message_id"], {})
        drafts.append(
            {
                "id": f"feedback-{item['message_id'] or 'unknown'}",
                "title": f"Draft eval from {item['category']} review item",
                "client_id": "maya",
                "message": entry.get("user_message", "<fill from transcript>"),
                "answer": entry.get("answer_preview", ""),
                "tool_calls": entry.get("tool_calls_used", []),
                "sources": entry.get("sources", []),
                "suggestions": entry.get("suggestions", []),
                "expected_tools": entry.get("tool_calls_used", []),
                "expected_sources": entry.get("sources", []),
                "forbidden_phrases": [],
                "quality": entry.get("quality") or {},
                "review_reasons": item["reasons"],
                "status": "draft_review_required",
            }
        )
    return drafts


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Allworth Quality Loop Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Release recommendation: **{report['release_recommendation']}**",
        "",
        "## Gates",
    ]
    for gate, ok in report["gates"].items():
        lines.append(f"- {'PASS' if ok else 'FAIL'}: {gate}")
    lines.extend(
        [
            "",
            "## Eval Summary",
            f"- Total: {report['evals']['total']}",
            f"- Passed: {report['evals']['passed']}",
            f"- Failed: {report['evals']['failed']}",
            f"- Average vision score: {report['evals']['average_score']}",
            "",
            "## Experience Metrics",
            f"- Memory-covered eval cases: {report['experience_metrics']['memory_used_cases']}",
            f"- Average suggestion score: {report['experience_metrics']['average_suggestion_score']}",
            "",
            "## MCP Summary",
            f"- Read-only smoke: {'PASS' if report['mcp']['ok'] else 'FAIL'}",
            f"- Exposed tool count: {report['mcp']['tool_count']}",
            "",
            "## Performance Smoke",
        ]
    )
    for result in report["performance"]["results"]:
        lines.append(
            f"- {'PASS' if result['passed'] else 'FAIL'}: {result['name']} "
            f"p50={result['p50_ms']}ms p95={result['p95_ms']}ms "
            f"budget={result['budget_ms']}ms workers={result['workers']}"
        )
    for error in report["performance"].get("errors", []):
        lines.append(f"- Performance error: {error}")
    lines.extend(
        [
            "",
            "## Frontend Static Smoke",
            f"- Advisor handoff copy: {'PASS' if report['frontend_static']['ok'] else 'FAIL'}",
            f"- Checked files: {report['frontend_static']['checked_files']}",
        ]
    )
    for error in report["frontend_static"].get("errors", []):
        lines.append(f"- Frontend static error: {error}")
    lines.extend(
        [
            "",
            "## Failed / Weak Eval Cases",
        ]
    )
    for error in report["mcp"].get("errors", []):
        lines.append(f"- MCP error: {error}")
    weak = [r for r in report["evals"]["results"] if not r["passed"]]
    if weak:
        for result in weak:
            lines.append(
                f"- {result['id']}: score {result['score']} missing={','.join(result['missing']) or 'none'}"
            )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Feedback Summary",
            f"- Total feedback: {report['feedback']['total']}",
            f"- Positive: {report['feedback']['positive']}",
            f"- Negative: {report['feedback']['negative']}",
            f"- Review items: {len(report['review_items'])}",
            "",
            "## Top Gaps",
        ]
    )
    for gap in report["top_gaps"] or ["No current gaps detected."]:
        lines.append(f"- {gap}")
    if report.get("live_evals") is not None:
        live = report["live_evals"]
        lines.extend(
            [
                "",
                "## Live Eval Summary",
                f"- Total: {live['total']}",
                f"- Passed: {live['passed']}",
                f"- Failed: {live['failed']}",
                f"- Skipped for budget: {live['skipped_for_budget']}",
                f"- Skipped estimated tokens: {live.get('skipped_estimated_tokens', 0)}",
                f"- Estimated tokens: {live['estimated_tokens']} / {live['max_estimated_tokens']}",
                f"- Timeout per case: {live['timeout_seconds']}s",
            ]
        )
        if live.get("error"):
            lines.append(f"- Error: {live['error']}")
        failed_live = [result for result in live.get("results", []) if not result.get("passed")]
        if failed_live:
            lines.append("")
            lines.append("### Live Eval Failures")
            for result in failed_live:
                details = []
                if result.get("error"):
                    details.append(f"error={result['error']}")
                if result.get("missing"):
                    details.append(f"missing={','.join(result['missing'])}")
                if result.get("safety_flags"):
                    details.append(f"safety={','.join(result['safety_flags'])}")
                if result.get("tool_actual") is not None:
                    details.append(f"tools={','.join(result['tool_actual']) or 'none'}")
                lines.append(
                    f"- {result.get('id', 'unknown')}: score {result.get('score', 0)}"
                    + (f" ({'; '.join(details)})" if details else "")
                )
                if result.get("answer_preview"):
                    lines.append(f"  Preview: {result['answer_preview']}")
    lines.append("")
    lines.append("## Next Best Action")
    lines.append(f"- {report['next_best_action']}")
    lines.append("")
    lines.append("## Proposed Improvements")
    for improvement in report["proposed_improvements"] or ["Keep monitoring scorecard and feedback trends."]:
        lines.append(f"- {improvement}")
    return "\n".join(lines) + "\n"


def write_report(path: Path | None = None) -> Path:
    report = build_quality_report()
    out = path or (Path(API_DIR).parent / "quality-loop-report.md")
    out.write_text(render_markdown_report(report))
    return out


def top_gaps(
    evals: dict[str, Any],
    review_items: list[dict[str, Any]],
    readiness: dict[str, Any] | None = None,
    mcp: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    frontend_static: dict[str, Any] | None = None,
) -> list[str]:
    counts: Counter[str] = Counter()
    for result in evals["results"]:
        counts.update(result.get("missing", []))
        counts.update(result.get("safety_flags", []))
    for item in review_items:
        counts.update(item["reasons"])
    if readiness and not readiness.get("ok", True):
        for check, ok in readiness.get("checks", {}).items():
            if not ok:
                counts.update([f"readiness:{check}"])
    if mcp and not mcp.get("ok", True):
        counts.update(["mcp"])
    if performance and not performance.get("ok", True):
        counts.update(["performance"])
    if frontend_static and not frontend_static.get("ok", True):
        counts.update(["frontend_static"])
    return [f"{name} ({count})" for name, count in counts.most_common(6)]


def experience_metrics(evals: dict[str, Any]) -> dict[str, Any]:
    results = evals.get("results", [])
    memory_used = sum(1 for result in results if result.get("memory_used"))
    suggestion_scores = [
        float(result["suggestion_score"])
        for result in results
        if result.get("suggestion_score") is not None
    ]
    average_suggestion_score = (
        round(sum(suggestion_scores) / len(suggestion_scores), 2) if suggestion_scores else 0.0
    )
    return {
        "memory_used_cases": memory_used,
        "average_suggestion_score": average_suggestion_score,
    }


def proposed_improvements(
    evals: dict[str, Any],
    review_items: list[dict[str, Any]],
    live_evals: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
    mcp: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    frontend_static: dict[str, Any] | None = None,
) -> list[str]:
    gaps = set()
    for result in evals["results"]:
        gaps.update(result.get("missing", []))
        gaps.update(result.get("safety_flags", []))
    for item in review_items:
        gaps.update(item["reasons"])
    if readiness and not readiness.get("ok", True):
        for check, ok in readiness.get("checks", {}).items():
            if not ok:
                gaps.add(f"readiness:{check}")
    if mcp and not mcp.get("ok", True):
        gaps.add("mcp")
    if performance and not performance.get("ok", True):
        gaps.add("performance")
    if frontend_static and not frontend_static.get("ok", True):
        gaps.add("frontend_static")
    if live_evals:
        if live_evals.get("total", 0) == 0 and live_evals.get("skipped_for_budget", 0) > 0:
            gaps.add("live_eval_budget_too_low")
        elif not live_evals.get("ok"):
            gaps.add("live_eval_failure")
        for result in live_evals.get("results", []):
            gaps.update(result.get("missing", []))
            gaps.update(result.get("safety_flags", []))
    proposals = []
    if "right_tool" in gaps or "missing:right_tool" in gaps or "missing_tool_calls" in gaps:
        proposals.append(
            "Tighten routing/tool descriptions and add a golden eval for the failing user intent."
        )
    if "exact_model_names" in gaps or "missing:exact_model_names" in gaps:
        proposals.append(
            "Force model names to be copied from rebalance tool output and add an AWF naming regression."
        )
    if "correct_advisor" in gaps or "missing:correct_advisor" in gaps or "safety:stale_advisor_name" in gaps:
        proposals.append(
            "Sanitize memory and derive advisor names from household data before prompting the LLM."
        )
    if (
        "suggestion_relevance" in gaps
        or "missing:suggestion_relevance" in gaps
        or "static_suggestions" in gaps
    ):
        proposals.append(
            "Generate follow-up suggestions from latest intent, sources, active nudges, and answer text."
        )
    if "sources_cited" in gaps or "missing:sources_cited" in gaps or "missing_sources" in gaps:
        proposals.append(
            "Require visible sources for substantive answers and block empty-source streamed responses."
        )
    if "safe_non_directive" in gaps or "missing:safe_non_directive" in gaps:
        proposals.append(
            "Add a safety repair pass for directive investment, tax, or legal language before "
            "streaming completion."
        )
    if any(gap.startswith("safety:") for gap in gaps):
        proposals.append("Promote the safety-flagged response into an eval fixture before release.")
    if "live_eval_failure" in gaps:
        proposals.append(
            "Fix live eval provider or Redis connectivity before using live GPT evals as a release gate."
        )
    if "live_eval_budget_too_low" in gaps:
        proposals.append(
            "Raise the live eval token budget or choose fewer/smaller targeted cases before release."
        )
    if "readiness:redisReachable" in gaps:
        proposals.append("Start or attach Redis, or disable CHAT_MEMORY_ENABLED for local offline runs.")
    if "mcp" in gaps:
        proposals.append("Restore the MCP read-only tool surface and provenance envelope.")
    if "performance" in gaps:
        proposals.append(
            "Profile the slow dashboard or financial-tool path, then cache only stable non-sensitive data."
        )
    if "frontend_static" in gaps:
        proposals.append(
            "Replace delivery-implying handoff copy with draft/prep language until a real "
            "advisor workflow exists."
        )
    return proposals


def next_best_action(
    evals: dict[str, Any],
    review_items: list[dict[str, Any]],
    live_evals: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
    mcp: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    frontend_static: dict[str, Any] | None = None,
) -> str:
    if readiness and not readiness.get("ok", True):
        if readiness.get("checks", {}).get("redisReachable") is False:
            return "Restore Redis reachability or disable chat memory before running live evals."
        return "Fix readiness checks before spending GPT tokens on live evals."
    if not evals["ok"]:
        return "Fix failing deterministic eval cases before changing product behavior."
    if mcp and not mcp.get("ok", True):
        return "Fix the MCP read-only boundary before release."
    if performance and not performance.get("ok", True):
        return "Profile and fix the slow core path before running live GPT evals."
    if frontend_static and not frontend_static.get("ok", True):
        return "Fix delivery-implying frontend copy before release."
    if (
        live_evals
        and live_evals.get("total", 0) == 0
        and live_evals.get("skipped_for_budget", 0) > 0
    ):
        return "Raise the live eval token budget or select a smaller targeted live eval case."
    if live_evals and not live_evals["ok"]:
        return "Inspect failed live GPT evals and convert the failures into deterministic fixtures."
    if review_items:
        return "Review feedback-derived draft fixtures and promote repeatable failures into eval cases."
    if not live_evals:
        return "Run a small budgeted live eval before the next release candidate."
    return "Expand the eval corpus with the next most common real client question."


def classify_review_item(reasons: list[str]) -> str:
    if any(reason.startswith("safety:") for reason in reasons):
        return "safety"
    if "low_vision_score" in reasons:
        return "llm_quality"
    if "missing_tool_calls" in reasons:
        return "tooling"
    if "missing_sources" in reasons:
        return "grounding"
    if "static_suggestions" in reasons:
        return "frontend_ux"
    return "llm_quality"
