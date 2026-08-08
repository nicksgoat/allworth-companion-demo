"""Deterministic NFBC math — the source of truth for numbers.

Claude (agent.py) reads tickets and proposes resolution/classification/reply,
but every dollar amount, period, and validation is computed HERE so the figures
are repeatable and auditable. Ported from the prototype's regex parsers
(nfbc-tool/wealth_mcp/web/app.py) and heuristic analysis (synapse.py::_analyze).

Pure functions only — no DB, no network — so this module is unit-testable.
"""

from __future__ import annotations

import datetime as _dt
import re

# Tokens that look like "LastName, FirstName" but are really column labels.
_NAME_STOPWORDS = {
    "net flows", "net flow", "flow adjustment", "adjustment type",
    "account value", "cash deposit", "cash withdrawal", "american funds",
    "new money",
}

# Ticket-jargon words that appear capitalized in summaries but are NOT names —
# used to keep summary name-extraction from searching on filler.
_SUMMARY_STOPWORDS = {
    "remove", "outflow", "outflows", "inflow", "inflows", "correction",
    "transition", "transitioned", "client", "clients", "departure", "adjustment",
    "adjustments", "missing", "many", "flow", "flows", "nfbc", "please",
    "account", "accounts", "review", "distribution", "name", "there", "under",
    "have", "idea", "think", "money", "into", "from", "with", "this", "that",
}

# Adjustment types seen on real tickets (free-form; Claude classifies, this is the menu).
ADJUSTMENT_TYPES = [
    "Net New",
    "courtesy",
    "RD Approval",
    "Account Processing Delay",
    "Transition",
    "Estate",
    "Correction",
]


# ── amount / name / candidate parsing ───────────────────────────────────────


def extract_amount(text: str) -> float | None:
    """Extract a dollar amount from a text segment.

    Handles 556k, $556,000, 556000, $1.2M, 182kish, etc. Scans anywhere.
    """
    if not text:
        return None

    m = re.search(r"(\d+(?:\.\d+)?)\s*([kKmM])(?:ish)?", text)
    if m:
        val = float(m.group(1))
        mult = m.group(2).lower()
        if mult == "k":
            return val * 1000
        if mult == "m":
            return val * 1_000_000

    m = re.search(r"\$?(\d[\d,]*(?:\.\d{1,2})?)", text)
    if m:
        cleaned = m.group(1).replace(",", "")
        if cleaned:
            val = float(cleaned)
            if val > 100:
                return val

    m = re.search(r"\b(\d{4,})\b", text)
    if m:
        return float(m.group(1))

    return None


def extract_ticket_amount(text: str) -> float | None:
    """Best-effort magnitude of a dollar amount stated in a ticket.

    Prefers ``$``-tagged amounts (e.g. ``-$819,430``, ``$556k``) over bare
    numbers so a Salesforce URL / trailing ``$0 0 0`` doesn't win. Returns a
    positive magnitude — the offset direction is decided by classification, and
    every value is human-verified before a write. Used only as a fallback when
    flow-based computation finds no amount.
    """
    if not text:
        return None
    for m in re.finditer(r"-?\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*([kKmM])?", text):
        cleaned = m.group(1).replace(",", "")
        if not cleaned:
            continue
        val = float(cleaned)
        suffix = (m.group(2) or "").lower()
        if suffix == "k":
            val *= 1000
        elif suffix == "m":
            val *= 1_000_000
        if val >= 100:
            return val
    return extract_amount(text)


def all_dollar_amounts(text: str) -> list[float]:
    """Every distinct ``$``-tagged amount (positive magnitude) in the text.

    Used to tell a single-client ticket (one amount → safe to auto-fill) from a
    multi-client one (several amounts → don't guess which is whose)."""
    out: list[float] = []
    for m in re.finditer(r"-?\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*([kKmM])?", text or ""):
        cleaned = m.group(1).replace(",", "")
        if not cleaned:
            continue
        val = float(cleaned)
        suffix = (m.group(2) or "").lower()
        if suffix == "k":
            val *= 1000
        elif suffix == "m":
            val *= 1_000_000
        if val >= 100:
            out.append(round(abs(val), 2))
    return out


def extract_named_amounts(text: str) -> list[dict]:
    """Pairs of ``{name, amount}`` from a multi-client ticket.

    Anchors on each capitalized "First Last" (tolerant of Jira's newline
    stripping, which glues a name to the preceding digits) and reads the first
    dollar amount in the segment up to the next name — so
    "William Jackson - IRA 2155 - $278,144.71 ... Lauren Kirkpatrick ... $359,618"
    yields one amount per client rather than the first amount for everyone.
    """
    if not text:
        return []
    names = list(re.finditer(
        r"(?<![A-Za-z])([A-Z][a-z]{2,}(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]{2,})", text))
    out: list[dict] = []
    for i, m in enumerate(names):
        seg_end = names[i + 1].start() if i + 1 < len(names) else len(text)
        amount = extract_ticket_amount(text[m.end():seg_end])
        if amount is not None:
            out.append({"name": m.group(1).strip(), "amount": round(abs(amount), 2)})
    return out


def household_ticket_amount(hh_name: str, ticket_text: str) -> float | None:
    """The ticket amount that belongs to a specific household, or None if it
    can't be pinned unambiguously.

    Matches a named amount when every significant token of the ticket name
    appears in the household name ("Lauren Kirkpatrick" -> "Kirkpatrick, Lauren").
    Falls back to the ticket's single amount only when the ticket is
    unambiguously about one amount; a multi-amount ticket with no clean match
    returns None so a wrong figure is never auto-filled.
    """
    hh = (hh_name or "").lower()
    named = extract_named_amounts(ticket_text)
    matched: set[float] = set()
    for na in named:
        tokens = [t for t in re.findall(r"[A-Za-z]{3,}", na["name"].lower())
                  if t not in _SUMMARY_STOPWORDS]
        if tokens and all(t in hh for t in tokens):
            matched.add(na["amount"])
    if len(matched) == 1:
        return matched.pop()
    if len(matched) > 1:
        return None  # this household maps to several amounts — needs a human
    distinct = set(all_dollar_amounts(ticket_text))
    if len(distinct) == 1:
        return distinct.pop()
    return None


def extract_sf_ids(text: str) -> list[str]:
    """Salesforce record IDs from a ticket — from Lightning URLs
    (``/lightning/r/<object>/<id>/``) or bare 15/18-char IDs. These resolve
    directly to a household via the dim's ``sfhhid``, so they're the most
    reliable disambiguator when a name is shared by several households."""
    if not text:
        return []
    ids: list[str] = []
    for m in re.finditer(r"/lightning/r/[^/]+/([A-Za-z0-9]{15,18})", text):
        ids.append(m.group(1))
    for m in re.finditer(r"(?<![A-Za-z0-9])(001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)(?![A-Za-z0-9])", text):
        ids.append(m.group(1))
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _account_hint(segment: str) -> str | None:
    """A custodian account number (or its trailing digits) from a text segment."""
    m = re.search(r"ending\s+(\d{3,})", segment, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{2,5}-\d{4,})\b", segment)
    if m:
        return m.group(1).replace("-", "")
    m = re.search(r"\b(\d{5,})\b", segment)
    if m:
        return m.group(1)
    return None


def extract_named_accounts(text: str) -> list[dict]:
    """Pairs of ``{name, account}`` — each "First Last" with the account number
    or "ending NNNN" in its segment. Used to disambiguate same-surname
    households (e.g. three William Jacksons) by the account the ticket cites."""
    if not text:
        return []
    names = list(re.finditer(
        r"(?<![A-Za-z])([A-Z][a-z]{2,}(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]{2,})", text))
    out: list[dict] = []
    for i, m in enumerate(names):
        seg_end = names[i + 1].start() if i + 1 < len(names) else len(text)
        acct = _account_hint(text[m.end():seg_end])
        if acct:
            out.append({"name": m.group(1).strip(), "account": acct})
    return out


def parse_client_lines(desc: str) -> list[dict]:
    """Parse a description for client name + amount patterns.

    Works on continuous text (Jira often strips newlines) by locating every
    "LastName, FirstName" and reading the amount from the segment up to the
    next name. Falls back to line-based "FirstName LastName Amount". Returns
    list of {name, amount, raw_line}.
    """
    desc = desc or ""
    clients: list[dict] = []
    seen: set[str] = set()

    pattern = re.compile(
        r"(?:^|(?<=[^A-Z]))"
        r"([A-Z][a-z]+(?:\s+(?:Jr|Sr|II|III|IV)\.?)?"
        r",\s*"
        r"[A-Z][a-z]+(?:\s+(?:and\s+)?[A-Z][a-z]+)*"
        r")",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(desc))
    for i, m in enumerate(matches):
        full_name = m.group(0).strip().rstrip(",;.")
        seg_start = m.end()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(desc)
        segment = desc[seg_start:seg_end]
        key = full_name.lower()
        if key in seen:
            continue
        seen.add(key)
        clients.append({
            "name": full_name,
            "amount": extract_amount(segment),
            "raw_line": f"{full_name} {segment[:80].strip()}",
        })

    if not clients:
        for line in desc.split("\n"):
            line = line.strip()
            if not line or len(line) < 4:
                continue
            m2 = re.match(r"^([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+[\$\d]", line)
            if not m2:
                continue
            name = m2.group(1).strip()
            if name.lower() in _NAME_STOPWORDS:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            clients.append({
                "name": name,
                "amount": extract_amount(line[m2.end() - 1:]),
                "raw_line": line,
            })

    return clients


def extract_candidates(ticket: dict) -> list[dict]:
    """Ranked search candidates from a ticket: {term, source, confidence} desc."""
    candidates: list[dict] = []
    summary = ticket.get("summary", "") or ""
    desc = ticket.get("description", "") or ""
    text = f"{summary} {desc}"

    def _add(term, source, confidence):
        if term and not any(c["term"] == term for c in candidates):
            candidates.append({"term": term, "source": source, "confidence": confidence})

    for m in re.finditer(r"(?:avhhid|HH\s*ID)[:\s#]*(\d{3,})", text, re.I):
        _add(m.group(1), "explicit_id", 100)
    for m in re.finditer(r"\b(\d{2,5}-\d{4,})", text):
        _add(m.group(1), "account_number", 97)
    for m in re.finditer(r"\b(\d{5,})\b", text):
        _add(m.group(1), "numeric_id", 95)

    m = re.match(r"^([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*[-–—]", summary)
    if m:
        _add(m.group(1), "summary_name_before_dash", 90)
    m = re.search(r"[-–—]\s*([A-Z][a-z]+ [A-Z][a-z]+(?:\.\s*[A-Z]\.?)?)\s*$", summary)
    if m:
        _add(m.group(1), "summary_name_after_dash", 85)
    m = re.match(
        r"^([A-Z][a-z]+ [A-Z][a-z]+)\s+(?:Transition|Net\s*Flow|NFBC|Adjust|Estate|Correct)",
        summary, re.I,
    )
    if m:
        _add(m.group(1), "summary_name_before_keyword", 80)

    # Household name(s) stated directly in the summary (e.g. "Sathyanarayana",
    # "Ken and Chris Benevides"). Surface capitalized name-runs whose tokens
    # aren't ticket jargon; the name-tolerant search reconciles "First Last" vs
    # the dim's "Last, First" and non-name junk simply matches nothing.
    for run in re.findall(r"\b([A-Z][a-z]+(?:\s+(?:and\s+)?[A-Z][a-z]+)*)\b", summary):
        toks = [w for w in run.split() if w.lower() != "and"]
        distinctive = [w for w in toks if len(w) >= 4 and w.lower() not in _SUMMARY_STOPWORDS]
        if distinctive:
            _add(run.strip(), "summary_name", 65)

    reporter = (ticket.get("reporter") or "").strip()
    _add(reporter, "reporter", 60)

    # Two-word names in the body. Jira often strips newlines and glues a name to
    # the preceding amount/date ("...2025Lauren Kirkpatrick"), so anchor on a
    # non-letter (not a word boundary, which a digit-letter run defeats).
    for m in re.finditer(r"(?<![A-Za-z])([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})", desc):
        name = m.group(1)
        if name.lower() in _NAME_STOPWORDS:
            continue
        _add(name, "description_name", 50)

    for comment in ticket.get("comments", []) or []:
        body = comment.get("body", "") or ""
        for m2 in re.finditer(r"(?:avhhid|HH\s*ID)[:\s#]*(\d{3,})", body, re.I):
            _add(m2.group(1), "comment_id", 75)
        for m2 in re.finditer(r"\b(\d{5,})\b", body):
            _add(m2.group(1), "comment_number", 70)

    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    return candidates


# ── period selection ─────────────────────────────────────────────────────────


def _month_end(d: _dt.date) -> _dt.date:
    """Last calendar day of ``d``'s month."""
    nxt = _dt.date(d.year + 1, 1, 1) if d.month == 12 else _dt.date(d.year, d.month + 1, 1)
    return nxt - _dt.timedelta(days=1)


def _prior_month_end(today: _dt.date | None = None) -> _dt.date:
    """Month-end of the month before ``today`` (the last closed comp period)."""
    today = today or _dt.date.today()
    return today.replace(day=1) - _dt.timedelta(days=1)


def to_month_end(period: str) -> str:
    """Normalize an ISO date (or ``YYYY-MM``) to that month's month-end ISO date.

    NFBC reporting periods are always month-end; a flow period is already
    month-end so this is idempotent, but it also repairs any first-of-month or
    mid-month value that slips through.
    """
    if not period:
        return period
    try:
        s = str(period)[:10]
        parts = s.split("-")
        year, month = int(parts[0]), int(parts[1])
        day = int(parts[2]) if len(parts) > 2 else 1
        return _month_end(_dt.date(year, month, day)).isoformat()
    except (ValueError, IndexError):
        return period


def select_period(flows: list[dict], ticket_text: str = "") -> str | None:
    """Pick a reporting period deterministically, always as a month-end date.

    year-in-ticket -> last flow period in that year -> last period with a
    positive inflow -> most recent flow period -> prior month-end (last closed
    comp period). Periods must be month-end; when the credit can't be tied to a
    specific offset flow, it books to the prior month's month-end rather than the
    current (still-open) month.
    """
    flows = flows or []
    year_match = re.search(r"\b(20[2-9]\d)\b", ticket_text or "")
    credit_year = year_match.group(1) if year_match else None

    if credit_year and flows:
        year_periods = [f["reportingperiod"] for f in flows
                        if str(f.get("reportingperiod", "")).startswith(credit_year)]
        if year_periods:
            return to_month_end(year_periods[-1])

    for f in reversed(flows):
        if f.get("inflows") and float(f["inflows"]) > 0:
            return to_month_end(f["reportingperiod"])

    if flows:
        return to_month_end(flows[-1]["reportingperiod"])

    return _prior_month_end().isoformat()


# ── analysis / recommendation ─────────────────────────────────────────────────


def analyze(investigation: dict) -> dict:
    """Findings + a recommended {amount, period, reasoning} from Synapse data.

    Mirrors the prototype heuristic: flag transitions, anomalous outflow
    periods (net < -$10k), and existing adjustments; recommend an offset.
    """
    dim = investigation.get("dim")
    flows = investigation.get("flows") or []
    adjustments = investigation.get("adjustments") or []
    fact = investigation.get("fact")

    findings: list[dict] = []

    if dim:
        prev = dim.get("previousadvisor") or ""
        curr = dim.get("sfadvisor") or ""
        if prev and prev != curr:
            findings.append({"type": "info", "title": "Transitioned Household",
                             "detail": f"Previous advisor: {prev} → Current: {curr}."})
        elif not prev:
            findings.append({"type": "warn", "title": "No Previous Advisor",
                             "detail": "previousadvisor is blank — may not have transitioned."})

    anomalous = []
    for f in flows:
        net = f.get("net_flows") or 0
        if net < -10000:
            anomalous.append({"period": f["reportingperiod"], "net": net})

    if anomalous:
        plist = ", ".join(p["period"] for p in anomalous)
        total = sum(p["net"] for p in anomalous)
        findings.append({"type": "warn",
                         "title": f"{len(anomalous)} Period(s) with Significant Outflows",
                         "detail": f"Periods: {plist}. Combined net flow: ${total:,.2f}."})
    elif flows:
        findings.append({"type": "success", "title": "No Significant Outflow Periods",
                         "detail": "All periods show normal flow patterns."})

    already_adjusted = sum(a.get("flow_adjustment") or 0 for a in adjustments)
    if adjustments:
        findings.append({"type": "warn", "title": f"{len(adjustments)} Existing Adjustment(s)",
                         "detail": f"Total adjusted: ${already_adjusted:,.2f}. Verify no duplication."})
    else:
        findings.append({"type": "success", "title": "No Existing Adjustments",
                         "detail": "No prior NFBC adjustments — safe to proceed."})

    if fact:
        ttm = fact.get("ttm_net_flows") or 0
        if ttm < -10000:
            findings.append({"type": "info", "title": f"TTM Net Flows: ${ttm:,.2f}",
                             "detail": "Significant negative TTM flow — likely needs offset."})

    recommendation = None
    if anomalous:
        raw = sum(p["net"] for p in anomalous)
        if not adjustments:
            recommendation = {
                "amount": round(-raw, 2),
                "period": anomalous[-1]["period"],
                "reasoning": f"Offset {len(anomalous)} anomalous period(s) totaling ${raw:,.2f}.",
            }
        else:
            remaining = -(raw + already_adjusted)
            if abs(remaining) > 100:
                recommendation = {
                    "amount": round(remaining, 2),
                    "period": anomalous[-1]["period"],
                    "reasoning": (f"Anomalous flows ${raw:,.2f}, existing adjustments "
                                  f"${already_adjusted:,.2f}. Remaining offset: ${remaining:,.2f}."),
                }

    return {"findings": findings, "recommendation": recommendation}


def credit_recommendation(parsed_amount: float | None, investigation: dict,
                          ticket_text: str = "") -> dict | None:
    """When the ticket names an explicit credit amount, recommend it minus existing adjustments."""
    if not parsed_amount:
        return None
    flows = investigation.get("flows") or []
    adjustments = investigation.get("adjustments") or []
    already_adjusted = sum(a.get("flow_adjustment") or 0 for a in adjustments)
    remaining = parsed_amount - already_adjusted
    if remaining <= 100:
        return None
    period = select_period(flows, ticket_text)
    note = ""
    if already_adjusted:
        note = (f" Existing adjustments total ${already_adjusted:,.0f}; "
                f"remaining: ${remaining:,.0f}.")
    return {
        "amount": round(remaining, 2),
        "period": period,
        "reasoning": f"Parsed credit of ${parsed_amount:,.0f} from ticket.{note}",
    }


# ── finalize: code wins on numbers ────────────────────────────────────────────


def finalize(claude_proposal: dict, investigation: dict, ticket: dict,
             parsed_amount: float | None = None) -> dict:
    """Produce the authoritative adjustment, recomputing numbers from data.

    Claude's `selected_avhhid` is validated against the candidate set; its
    proposed amount/period are IGNORED in favor of code's computation. A
    material disagreement is surfaced via `needs_human` rather than silently
    accepting Claude's figure.
    """
    ticket_text = f"{ticket.get('summary','')} {ticket.get('description','')}"
    needs_human: list[str] = list(claude_proposal.get("needs_human_flags") or [])

    dim = investigation.get("dim") or {}
    resolved_avhhid = dim.get("avhhid")
    if resolved_avhhid is None:
        needs_human.append("No household resolved from Synapse.")

    analysis = analyze(investigation)
    rec = analysis.get("recommendation")
    if rec is None:
        rec = credit_recommendation(parsed_amount, investigation, ticket_text)

    code_amount = rec["amount"] if rec else None
    code_period = (to_month_end(rec["period"]) if rec
                   else select_period(investigation.get("flows") or [], ticket_text))
    code_reasoning = rec["reasoning"] if rec else "No anomalous flows or parsed amount; manual review."

    # Fallback: when flow-based computation finds no amount, use the dollar
    # amount stated in the ticket for THIS household (deterministic regex over
    # ticket text — NOT Claude's number). On a multi-client ticket each
    # household gets its own amount; if it can't be pinned unambiguously the
    # amount is left blank for manual entry rather than guessed. Flagged for
    # human verification; nothing is written without an explicit confirm.
    if code_amount is None:
        hh_amount = household_ticket_amount(dim.get("sfhhname") or "", ticket_text)
        if hh_amount:
            code_amount = round(abs(hh_amount), 2)
            code_reasoning = (
                f"Amount ${code_amount:,.2f} taken from the ticket for "
                f"{dim.get('sfhhname') or 'this household'}; no matching anomalous "
                f"flow was found — verify against flows before confirming."
            )
            needs_human.append(
                "Amount taken from the ticket text, not computed from flows — verify."
            )
        elif len(set(all_dollar_amounts(ticket_text))) > 1:
            needs_human.append(
                "Ticket lists multiple client amounts — enter this household's amount manually."
            )

    if code_amount is None:
        needs_human.append("Code could not compute an amount; enter it manually.")

    # Compare Claude's read to code's authoritative number (informational only).
    claude_amount = claude_proposal.get("proposed_amount")
    computed_vs_claude = {"claude_amount": claude_amount, "code_amount": code_amount}
    if (claude_amount is not None and code_amount is not None
            and abs(float(claude_amount) - float(code_amount)) > max(100.0, 0.05 * abs(code_amount))):
        needs_human.append(
            f"Claude proposed ${float(claude_amount):,.0f} but code computed "
            f"${float(code_amount):,.0f} — verify."
        )

    adj_type = (claude_proposal.get("adjustment_type") or "Net New").strip() or "Net New"

    return {
        "avhhid": resolved_avhhid,
        "household": dim.get("sfhhname"),
        "advisor": dim.get("sfadvisor"),
        "period": code_period,
        "amount": code_amount,
        "multiplier": 1,
        "adjustment_type": adj_type,
        "rationale": claude_proposal.get("rationale") or code_reasoning,
        "draft_reply": claude_proposal.get("draft_reply") or "",
        "confidence": claude_proposal.get("confidence"),
        "findings": analysis.get("findings", []),
        "computed_vs_claude": computed_vs_claude,
        "needs_human_flags": needs_human,
    }
