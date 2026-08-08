"""Flask blueprint for NFBC — mounted at /api/nfbc by backend/app.py.

The UI is the React SPA served at /nfbc (nginx); it calls these JSON endpoints
under the shared /api base. Endpoints:

  GET    /api/nfbc/queue?status=open&refresh=0   build/return the proposal queue
  PUT    /api/nfbc/queue/<row_id>                 edit a row (amount/period/type/reply)
  POST   /api/nfbc/queue/<row_id>/confirm         LIVE write -> rollforward -> Jira reply -> Done
  GET    /api/nfbc/audit                          DB adjustments + action history
  GET    /api/nfbc/health
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Thread

from flask import Blueprint, jsonify, request

from nfbc import agent, jira_client, queue_store as store, synapse_nfbc as syn

logger = logging.getLogger(__name__)

bp = Blueprint("nfbc", __name__)

# ── queue cache ───────────────────────────────────────────────────────────────
import os

_QUEUE_TTL = int(os.getenv("NFBC_QUEUE_TTL_SECONDS", "600"))
_BUILD_WORKERS = int(os.getenv("NFBC_BUILD_WORKERS", "4"))
_queue_cache: dict = {
    "built_at": 0.0, "rows": None, "status": None,
    "building": False, "build_error": None, "jql_ticket_count": None,
    "progress": None,  # {"done": n, "total": m, "current": "AI-1234"}
}
_cache_lock = Lock()


def _coerce_float(v, default=0.0):
    if v is None or v == "":
        return default
    try:
        n = float(v)
        return default if math.isnan(n) else n
    except (TypeError, ValueError):
        return default


def _coerce_int(v, default=0):
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ── queue ───────────────────────────────────────────────────────────────────


def _build_queue(status: str, force: bool = False) -> None:
    """Build the proposal queue in a background thread; results land in the cache.

    Runs Jira search + per-ticket detail/agent analysis, which can take minutes —
    far longer than the nginx/App Service proxy timeout, hence async. Each
    ticket's finalized rows are cached durably in Synapse keyed by a
    change-fingerprint, so a rebuild only re-runs the expensive LLM+Synapse work
    for tickets that actually changed. ``force`` bypasses the cache (full rebuild).
    """
    try:
        tickets = jira_client.search_nfbc_tickets(status)

        # Resolve the active LLM provider/model once for build telemetry.
        _diag = agent.diagnostics()
        _prov, _model = _diag.get("provider"), _diag.get("model")
        reused = 0

        def _rows_for(ticket: dict) -> list[dict]:
            nonlocal reused
            detail = jira_client.get_ticket_detail(ticket["key"]) or ticket
            fp = _ticket_fingerprint(detail)
            if not force:
                cached = syn.get_cached_build(ticket["key"])
                if cached and cached.get("fingerprint") == fp and cached.get("rows"):
                    reused += 1
                    return cached["rows"]
            t0 = time.time()
            try:
                rows = agent.propose_for_ticket(detail)
            except Exception as exc:
                logger.exception("propose_for_ticket failed for %s", ticket.get("key"))
                return [{
                    "row_id": f"{ticket.get('key')}:error",
                    "ticket_key": ticket.get("key"),
                    "ticket_summary": ticket.get("summary"),
                    "ticket_status": ticket.get("status"),
                    "avhhid": None, "household": None, "advisor": None,
                    "period": None, "amount": None, "adjustment_type": "Net New",
                    "rationale": f"Analysis failed: {exc}", "draft_reply": "",
                    "confidence": 0.0, "needs_human_flags": [str(exc)],
                    "status": "error",
                }]
            build_ms = int((time.time() - t0) * 1000)
            # Only cache fully-resolved proposals — unresolved/error tickets must
            # retry on the next build (a needs_review row is a failed resolution,
            # not a stable analysis worth reusing).
            if rows and all(r.get("status") == "proposed" for r in rows):
                syn.save_cached_build(ticket["key"], fp, rows, build_ms,
                                      _prov, _model, "queue-build")
            return rows

        # Analyze tickets concurrently — each one costs several Synapse queries
        # plus a Claude call, so serial builds take far too long.
        by_key: dict[str, list[dict]] = {}
        done = 0
        with ThreadPoolExecutor(max_workers=_BUILD_WORKERS) as pool:
            futures = {pool.submit(_rows_for, t): t for t in tickets}
            for fut in as_completed(futures):
                t = futures[fut]
                by_key[t["key"]] = fut.result()
                done += 1
                with _cache_lock:
                    _queue_cache["progress"] = {"done": done, "total": len(tickets),
                                                "current": t.get("key")}

        # Preserve Jira result order for a stable UI.
        rows: list[dict] = []
        for t in tickets:
            rows.extend(by_key.get(t["key"], []))

        # Merge any persisted confirmed/edited state over freshly-proposed rows.
        persisted = {p["row_id"]: p for p in store.all_proposals() if p.get("row_id")}
        for row in rows:
            prev = persisted.get(row.get("row_id"))
            if prev and prev.get("status") in ("confirmed", "written_pending_jira"):
                row["status"] = prev["status"]
                row["confirm_result"] = prev.get("confirm_result")

        store.save_proposals(rows)
        logger.info("NFBC queue build: %d tickets, %d reused from cache, %d recomputed",
                    len(tickets), reused, len(tickets) - reused)

        with _cache_lock:
            _queue_cache.update({
                "built_at": time.time(), "rows": rows, "status": status,
                "building": False, "build_error": None,
                "jql_ticket_count": len(tickets), "progress": None,
            })
    except Exception as exc:
        logger.exception("NFBC queue build failed")
        with _cache_lock:
            _queue_cache.update({"building": False, "build_error": str(exc),
                                 "progress": None})


def _ticket_fingerprint(detail: dict) -> str:
    """Stable hash of the ticket fields that affect a proposal. When unchanged,
    the cached rows are reused instead of re-running the LLM + Synapse work."""
    basis = "\x1f".join([
        str(detail.get("summary", "") or ""),
        str(detail.get("status", "") or ""),
        str(detail.get("updated", "") or ""),
        str(detail.get("description", "") or ""),
        str(len(detail.get("comments") or [])),
    ])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


@bp.get("/queue")
def get_queue():
    """Return the queue if built; otherwise kick off/report an async build.

    Responses:
      200 {ok, rows, ...}                 — fresh (or stale-but-usable) queue
      202 {ok, building: true, ...}       — build in progress; client should poll
      502 {ok: false, error, diag}        — last build failed
    """
    status = request.args.get("status", "open")
    refresh = request.args.get("refresh", "0") in ("1", "true", "yes")

    with _cache_lock:
        fresh = (
            _queue_cache["rows"] is not None
            and _queue_cache["status"] == status
            and (time.time() - _queue_cache["built_at"]) < _QUEUE_TTL
        )
        if fresh and not refresh:
            return jsonify({"ok": True, "cached": True,
                            "built_at": _queue_cache["built_at"],
                            "rows": _queue_cache["rows"],
                            "jql_ticket_count": _queue_cache["jql_ticket_count"],
                            "diag": jira_client.diagnostics()})

        if _queue_cache["building"]:
            return jsonify({"ok": True, "building": True,
                            "progress": _queue_cache["progress"],
                            "rows": _queue_cache["rows"] or [],
                            "diag": jira_client.diagnostics()}), 202

        if _queue_cache["build_error"] and not refresh and _queue_cache["rows"] is None:
            err = _queue_cache["build_error"]
            _queue_cache["build_error"] = None  # allow next poll to retry
            return jsonify({"ok": False, "error": err,
                            "diag": jira_client.diagnostics()}), 502

        _queue_cache["building"] = True
        _queue_cache["build_error"] = None

    Thread(target=_build_queue, args=(status, refresh), daemon=True,
           name="nfbc-queue-build").start()
    return jsonify({"ok": True, "building": True,
                    "rows": _queue_cache["rows"] or [],
                    "diag": jira_client.diagnostics()}), 202


@bp.put("/queue/<path:row_id>")
def edit_row(row_id: str):
    body = request.get_json(silent=True) or {}
    patch: dict = {}
    if "amount" in body:
        patch["amount"] = _coerce_float(body["amount"])
    if "period" in body:
        patch["period"] = (body["period"] or "").strip()
    if "adjustment_type" in body:
        patch["adjustment_type"] = (body["adjustment_type"] or "Net New").strip() or "Net New"
    if "multiplier" in body:
        patch["multiplier"] = _coerce_int(body["multiplier"], 1)
    if "draft_reply" in body:
        patch["draft_reply"] = body["draft_reply"] or ""
    if "avhhid" in body:
        patch["avhhid"] = _coerce_int(body["avhhid"]) or None

    row = store.update_proposal(row_id, patch)
    if row is None:
        return jsonify({"ok": False, "error": "row not found"}), 404

    # also reflect into the live cache so the next GET (cached) shows edits
    with _cache_lock:
        if _queue_cache["rows"]:
            for r in _queue_cache["rows"]:
                if r.get("row_id") == row_id:
                    r.update(patch)

    store.append_event({
        "action": "edit", "row_id": row_id,
        "user": store.user_from_headers(request.headers), "patch": patch,
    })
    return jsonify({"ok": True, "row": row, "validation": _validate(row)})


def _validate(row: dict) -> dict:
    warnings = []
    if not row.get("avhhid"):
        warnings.append("No household (avhhid) set.")
    if not row.get("period"):
        warnings.append("No reporting period set.")
    amt = row.get("amount")
    if amt is None or float(amt) == 0.0:
        warnings.append("Amount is empty or zero.")
    return {"ok": not warnings, "warnings": warnings}


def _attributed_comment(body: str, user: str) -> str:
    """Attribute the reply to the person who confirmed it.

    Jira comments are posted via a single shared API account, so every comment
    would otherwise appear authored by that service user. Stamping the acting
    user (from the app's authenticated session) into the body makes it clear who
    actually recorded the adjustment.
    """
    body = (body or "").strip()
    who = user if user and user != "anonymous" else None
    footer = (f"Recorded by {who} via the NFBC Adjustment Console."
              if who else "Recorded via the NFBC Adjustment Console.")
    return f"{body}\n\n— {footer}" if body else f"— {footer}"


# ── confirm (LIVE) ────────────────────────────────────────────────────────────


@bp.post("/queue/<path:row_id>/confirm")
def confirm_row(row_id: str):
    body = request.get_json(silent=True) or {}
    resume = bool(body.get("resume"))
    user = store.user_from_headers(request.headers)

    row = store.get_proposal(row_id)
    if row is None:
        return jsonify({"ok": False, "error": "row not found — rebuild the queue"}), 404
    if row.get("status") == "confirmed":
        return jsonify({"ok": False, "error": "row already confirmed",
                        "confirm_result": row.get("confirm_result")}), 409

    v = _validate(row)
    if not v["ok"]:
        return jsonify({"ok": False, "error": "validation failed", "validation": v}), 422

    avhhid = int(row["avhhid"])
    period = row["period"]
    amount = float(row["amount"])
    multiplier = int(row.get("multiplier") or 1)
    adj_type = row.get("adjustment_type") or "Net New"
    ticket_key = row.get("ticket_key")
    draft_reply = row.get("draft_reply") or ""

    steps: dict = (row.get("confirm_result") or {}).get("steps", {}) if resume else {}
    db_done = resume and steps.get("insert", {}).get("done")

    # 1. duplicate guard + 2. insert (skip if resuming after a DB write). The
    # rollforward stored procedures are NOT run here — the warehouse is no longer
    # refreshed same-day; the adjustment is picked up by the scheduled load.
    if not db_done:
        try:
            existing = syn.get_adjustments_for(avhhid)
            dup = any(
                a.get("reportingperiod") == period
                and abs((a.get("flow_adjustment") or 0) - amount) < 0.01
                and (a.get("adjustment_type") or "") == adj_type
                for a in existing
            )
            if dup:
                steps["insert"] = {"done": True, "already_present": True, "rows_affected": 0}
            else:
                rows_affected = syn.insert_adjustment(avhhid, period, amount, adj_type, multiplier)
                steps["insert"] = {"done": True, "already_present": False, "rows_affected": rows_affected}
            store.append_event({"action": "insert", "row_id": row_id, "user": user,
                                "avhhid": avhhid, "period": period, "amount": amount,
                                "adjustment_type": adj_type, "result": steps["insert"]})
        except Exception as exc:
            logger.exception("insert_adjustment failed for %s", row_id)
            steps["insert"] = {"done": False, "error": str(exc)}
            store.set_status(row_id, "error", {"confirm_result": {"steps": steps}})
            store.append_event({"action": "insert_error", "row_id": row_id, "user": user, "error": str(exc)})
            return jsonify({"ok": False, "partial_failure": True, "steps": steps,
                            "error": f"DB insert failed: {exc}"}), 500

    # 5. Jira comment
    if not steps.get("jira_comment", {}).get("done"):
        try:
            comment_body = _attributed_comment(draft_reply, user)
            steps["jira_comment"] = {"done": True, **jira_client.add_comment(ticket_key, comment_body)}
            store.append_event({"action": "jira_comment", "row_id": row_id, "user": user,
                                "ticket": ticket_key, "result": steps["jira_comment"]})
        except jira_client.JiraError as exc:
            steps["jira_comment"] = {"done": False, "error": str(exc)}
            store.set_status(row_id, "written_pending_jira", {"confirm_result": {"steps": steps}})
            return jsonify({"ok": False, "partial_failure": True, "steps": steps,
                            "error": f"Adjustment written; Jira comment failed: {exc}. Resume to retry."}), 502

    # 6. transition to Done
    if not steps.get("jira_transition", {}).get("done"):
        try:
            steps["jira_transition"] = {"done": True, **jira_client.transition_issue(ticket_key, target_status="Done")}
            store.append_event({"action": "jira_transition", "row_id": row_id, "user": user,
                                "ticket": ticket_key, "result": steps["jira_transition"]})
        except jira_client.JiraError as exc:
            steps["jira_transition"] = {"done": False, "error": str(exc)}
            store.set_status(row_id, "written_pending_jira", {"confirm_result": {"steps": steps}})
            return jsonify({"ok": False, "partial_failure": True, "steps": steps,
                            "error": f"Comment posted; transition to Done failed: {exc}. Resume to retry."}), 502

    result = {"steps": steps}
    store.set_status(row_id, "confirmed", {"confirm_result": result, "confirmed_by": user,
                                           "confirmed_at": store.now_iso()})
    with _cache_lock:
        if _queue_cache["rows"]:
            for r in _queue_cache["rows"]:
                if r.get("row_id") == row_id:
                    r["status"] = "confirmed"
                    r["confirm_result"] = result
    store.append_event({"action": "confirmed", "row_id": row_id, "user": user})
    return jsonify({"ok": True, "row_id": row_id, "partial_failure": False, "steps": steps})


# ── audit ─────────────────────────────────────────────────────────────────────


@bp.get("/audit")
def audit():
    try:
        db_adjustments = syn.get_all_adjustments()
    except Exception as exc:
        logger.exception("audit DB fetch failed")
        db_adjustments = []
    # Confirmed proposals carry the FULL process detail (ticket, flows, rationale,
    # posted reply, and confirm_result step flow) that the flat Synapse rows lack.
    confirmed = [
        p for p in store.all_proposals()
        if p.get("status") in ("confirmed", "written_pending_jira")
    ]
    confirmed.sort(key=lambda p: p.get("confirmed_at") or "", reverse=True)
    return jsonify({"ok": True, "db_adjustments": db_adjustments,
                    "confirmed": confirmed,
                    "actions": store.global_history()})


@bp.get("/household/<avhhid>")
def household(avhhid: str):
    """Live investigation for any household — dim, 12-month flows, existing
    adjustments, TTM fact — so a past adjustment written outside the console can
    still be inspected with full flow detail + account-value reconciliation.
    """
    try:
        inv = syn.investigate_household(avhhid)
    except Exception as exc:
        logger.exception("household investigation failed for %s", avhhid)
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"ok": True, **inv})


@bp.get("/health")
def health():
    diag = jira_client.diagnostics()
    return jsonify({"status": "ok", "jira": diag, "llm": agent.diagnostics()})


@bp.get("/build-stats")
def build_stats():
    """Per-ticket build telemetry (slowest first) from the durable cache — used
    to see which tickets dominate a queue build so the pipeline can be tuned."""
    return jsonify({"ok": True, "stats": syn.build_stats()})
