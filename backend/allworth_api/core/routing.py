"""Signal-based intent routing — maps natural-language queries to tool names.

Inspired by the analytics plugin's routing_kernel.py. Each tool gets a set of
signal phrases; route_intent() returns the best match(es) so the LLM (or a
client) can discover which tool to call without trial-and-error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RouteMatch:
    tool: str
    score: int  # number of matched signals
    signals: list[str]


# ── Signal definitions (one tuple per tool) ──────────────────────────

TOOL_SIGNALS: dict[str, tuple[str, ...]] = {
    "get_accounts": (
        "accounts",
        "balance",
        "net worth",
        "held away",
        "outside accounts",
        "managed assets",
        "allworth total",
        "how much do i have",
        "liabilities",
    ),
    "get_portfolio": (
        "portfolio",
        "holdings",
        "positions",
        "tax lots",
        "cost basis",
        "allocation",
        "concentration",
        "stocks",
        "bonds",
        "AAPL",
        "apple shares",
    ),
    "get_financial_plan": (
        "plan",
        "financial plan",
        "goals",
        "retirement",
        "lake house",
        "529",
        "income plan",
        "spending assumption",
    ),
    "get_spending": (
        "spending",
        "expenses",
        "budget",
        "over plan",
        "monthly spending",
        "categories",
        "travel",
        "how much am i spending",
    ),
    "get_client_profile": (
        "profile",
        "what do you know about me",
        "preferences",
        "memory",
        "what have you learned",
        "facts about me",
    ),
    "update_client_profile": (
        "remember",
        "save this",
        "note that",
        "keep in mind",
        "update my profile",
    ),
    "simulate_tax_impact": (
        "tax",
        "capital gains",
        "tax impact",
        "sell",
        "liquidate",
        "cost basis",
        "tax drag",
        "tax estimate",
        "if i sold",
    ),
    "get_advisor_brief": (
        "advisor brief",
        "talking points",
        "prepare for meeting",
        "client summary",
        "advisor view",
        "brief",
    ),
    "run_retirement_projection": (
        "retirement",
        "monte carlo",
        "projection",
        "will my money last",
        "run out of money",
        "success rate",
        "longevity",
        "how long will my portfolio last",
        "retirement readiness",
        "sustainable",
    ),
    "analyze_portfolio_drift": (
        "drift",
        "rebalance",
        "allocation",
        "off target",
        "overweight",
        "underweight",
        "asset mix",
        "60/40",
        "portfolio balance",
    ),
    "run_roth_conversion_analysis": (
        "roth",
        "roth conversion",
        "convert ira",
        "ira to roth",
        "backdoor",
        "tax bracket",
        "bracket impact",
        "irmaa",
    ),
    "analyze_goal_funding": (
        "goal",
        "goals",
        "lake house",
        "529",
        "on track",
        "funded",
        "goal progress",
        "how are my goals",
    ),
    "analyze_income_sustainability": (
        "income",
        "sustainable",
        "income plan",
        "can i afford",
        "draw rate",
        "cash runway",
        "will my income last",
        "spending vs income",
        "outlive",
    ),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _match_signals(signals: tuple[str, ...], text: str) -> list[str]:
    """Return signal phrases found in the query text (prefix-aware)."""
    hits = []
    for signal in signals:
        sig = signal.lower()
        # Use word-start boundary so "sell" matches "selling"
        if sig[0].isalpha():
            pattern = r"(?<!\w)" + re.escape(sig)
        else:
            pattern = re.escape(sig)
        if re.search(pattern, text):
            hits.append(signal)
    return hits


def route_intent(query: str, *, top_n: int = 3) -> list[RouteMatch]:
    """Return the top-N tool matches for a natural-language query.

    Each match includes the tool name, how many signals fired, and which ones.
    Returns an empty list if nothing matches.
    """
    text = _normalize(query)
    if not text:
        return []

    matches: list[RouteMatch] = []
    for tool, signals in TOOL_SIGNALS.items():
        hits = _match_signals(signals, text)
        if hits:
            matches.append(RouteMatch(tool=tool, score=len(hits), signals=hits))

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:top_n]
