"""Run the Allworth quality loop and write a Markdown report."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from allworth_api.core.eval_runner import run_live_eval_suite
from allworth_api.core.quality_loop import build_quality_report, render_markdown_report
from allworth_api.core.system_status import readiness_status


class LiveEvalDeadlineExceededError(TimeoutError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Allworth quality-loop gates.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--out", help="Optional path to write the Markdown report.")
    parser.add_argument("--json-out", help="Optional path to write the structured JSON report.")
    parser.add_argument("--live", action="store_true", help="Opt in to budgeted live GPT evals.")
    parser.add_argument("--live-max-cases", type=int, default=3, help="Max live eval prompts to run.")
    parser.add_argument(
        "--live-case-id",
        action="append",
        default=[],
        help="Run only the named eval case. Repeat or comma-separate for multiple cases.",
    )
    parser.add_argument(
        "--live-token-budget",
        type=int,
        default=8000,
        help="Estimated token budget for live eval prompts and answers.",
    )
    parser.add_argument(
        "--live-timeout-seconds",
        type=float,
        default=60.0,
        help="Wall-clock timeout per live eval case.",
    )
    parser.add_argument(
        "--live-chat-max-tokens",
        type=int,
        default=None,
        help="Optional temporary LLM_CHAT_MAX_TOKENS override for live evals.",
    )
    args = parser.parse_args()

    live_evals = None
    if args.live:
        if args.live_chat_max_tokens is not None:
            os.environ["LLM_CHAT_MAX_TOKENS"] = str(max(256, args.live_chat_max_tokens))
        live_evals = run_live_evals_with_deadline(args)
    report = build_quality_report(live_evals=live_evals)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        markdown = render_markdown_report(report)
        print(markdown)
        if args.out:
            Path(args.out).write_text(markdown)
    return 0 if report["ok"] else 1


def run_live_evals_with_deadline(args: argparse.Namespace) -> dict:
    readiness = readiness_status()
    if not readiness.get("ok", False):
        failed_checks = [
            check for check, ok in readiness.get("checks", {}).items() if not ok
        ]
        return live_eval_failure(
            args,
            error="live eval preflight failed: " + ", ".join(failed_checks),
        )

    deadline = max(1, math.ceil(args.live_timeout_seconds * max(args.live_max_cases, 1) + 5))
    previous_handler = None
    if hasattr(signal, "SIGALRM"):
        previous_handler = signal.getsignal(signal.SIGALRM)

        def _raise_timeout(_signum, _frame):
            raise LiveEvalDeadlineExceededError(f"live eval deadline exceeded after {deadline}s")

        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(deadline)
    try:
        return asyncio.run(
            run_live_eval_suite(
                max_cases=args.live_max_cases,
                max_estimated_tokens=args.live_token_budget,
                timeout_seconds=args.live_timeout_seconds,
                case_ids=live_case_ids(args),
            )
        )
    except TimeoutError as err:
        return live_eval_failure(args, error=str(err))
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            if previous_handler is not None:
                signal.signal(signal.SIGALRM, previous_handler)


def live_eval_failure(args: argparse.Namespace, *, error: str) -> dict:
    return {
        "ok": False,
        "mode": "live",
        "total": 0,
        "passed": 0,
        "failed": 1,
        "skipped_for_budget": 0,
        "skipped_estimated_tokens": 0,
        "average_score": 0,
        "estimated_tokens": 0,
        "max_estimated_tokens": args.live_token_budget,
        "timeout_seconds": args.live_timeout_seconds,
        "error": error,
        "results": [],
    }


def live_case_ids(args: argparse.Namespace) -> list[str] | None:
    case_ids = []
    for raw in args.live_case_id:
        case_ids.extend(case_id.strip() for case_id in raw.split(",") if case_id.strip())
    return case_ids or None


if __name__ == "__main__":
    raise SystemExit(main())
