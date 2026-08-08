"""Mock end-to-end tests for the NFBC Adjustment Console.

Covers the productionalized pipeline without touching live Synapse or Jira:
- deterministic math (month-end periods, amount extraction, per-client mapping)
- the comma-only crash regression
- name-order-tolerant household resolution
- multi-client row building + de-duplication
- the full confirm flow: DB insert -> rollforward -> attributed Jira comment ->
  transition, asserting the acting user is stamped into the comment.

Run from the backend/ directory:

    python -m pytest tests/test_nfbc.py -v
"""
from __future__ import annotations

import datetime as dt
import os
from unittest.mock import MagicMock, patch

import pytest

# Disable auth so the confirm route is reachable without a JWT.
os.environ["AUTH_DISABLE"] = "1"

from nfbc import compute, synapse_nfbc as syn  # noqa: E402


# ---------------------------------------------------------------------------
# Deterministic math — periods
# ---------------------------------------------------------------------------

def test_to_month_end_normalizes():
    assert compute.to_month_end("2025-11-30") == "2025-11-30"      # idempotent
    assert compute.to_month_end("2025-11-01") == "2025-11-30"      # first-of-month
    assert compute.to_month_end("2025-02") == "2025-02-28"         # year-month
    assert compute.to_month_end("2024-02-10") == "2024-02-29"      # leap year


def test_prior_month_end_fallback():
    assert compute._prior_month_end(dt.date(2026, 7, 27)).isoformat() == "2026-06-30"
    # No flows -> books to prior (closed) month-end, never a first-of-month.
    p = compute.select_period([])
    assert p.endswith(("-28", "-29", "-30", "-31"))


def test_select_period_prefers_offset_month_end():
    flows = [{"reportingperiod": "2026-06-30", "inflows": 0},
             {"reportingperiod": "2026-07-24", "inflows": 100}]
    assert compute.select_period(flows) == "2026-07-31"


# ---------------------------------------------------------------------------
# Deterministic math — amounts (incl. the comma-only crash regression)
# ---------------------------------------------------------------------------

def test_extract_amount_no_crash_on_comma_only():
    # Regex used to match a lone comma -> float("") ValueError. Must not raise.
    assert compute.extract_amount(", , ,") is None
    assert compute.extract_ticket_amount("$,") is None


def test_extract_ticket_amount_prefers_tagged():
    assert compute.extract_ticket_amount("-$819,430 Jul 2026 ... $0 0 0") == 819430.0
    assert compute.extract_ticket_amount("credit of $556k please") == 556000.0


def test_all_dollar_amounts_distinct():
    amts = compute.all_dollar_amounts("A $278,144.71 B $250,000 C $0")
    assert 278144.71 in amts and 250000.0 in amts and 0.0 not in amts


def test_extract_named_amounts_per_client():
    text = ("William Jackson - IRA 2155 - $278,144.71 deposit "
            "Lauren Kirkpatrick - IRA 0077 - $359,618 deposit")
    named = compute.extract_named_amounts(text)
    by = {n["name"]: n["amount"] for n in named}
    assert by.get("William Jackson") == 278144.71
    assert by.get("Lauren Kirkpatrick") == 359618.0


def test_household_ticket_amount_matches_by_name():
    text = ("William Jackson - $278,144.71 "
            "Lauren Kirkpatrick - $359,618")
    assert compute.household_ticket_amount("Kirkpatrick, Lauren", text) == 359618.0
    assert compute.household_ticket_amount("Jackson, William and Rebecca", text) == 278144.71


def test_household_ticket_amount_refuses_ambiguous():
    # A joint household matching two different amounts must NOT guess.
    text = ("Vicki Kirkpatrick - $1,426,188 "
            "John Kirkpatrick - $1,102,027")
    assert compute.household_ticket_amount("Kirkpatrick, John and Vicki", text) is None


# ---------------------------------------------------------------------------
# finalize — code owns the number + month-end period
# ---------------------------------------------------------------------------

def test_finalize_uses_household_amount_and_month_end_period():
    ticket = {"summary": "Remove Outflow", "description": "-$819,430 Jul 2026 Kipling, Randy"}
    investigation = {
        "dim": {"avhhid": "169981", "sfhhname": "Kipling, Randy", "sfadvisor": "Britton Riley"},
        "flows": [{"reportingperiod": "2026-06-30", "inflows": 0, "net_flows": 0},
                  {"reportingperiod": "2026-07-24", "inflows": 0, "outflows": -819430.13, "net_flows": 0}],
        "adjustments": [],
    }
    proposal = {"selected_avhhid": 169981, "adjustment_type": "Correction",
                "rationale": "firm-initiated", "draft_reply": "", "confidence": 0.9}
    final = compute.finalize(proposal, investigation, ticket)
    assert final["avhhid"] == "169981"
    assert final["amount"] == 819430.0            # from ticket text, not Claude
    assert final["period"] == "2026-07-31"        # month-end of the offset month
    assert any("verify" in f.lower() for f in final["needs_human_flags"])


# ---------------------------------------------------------------------------
# Household resolution — name-order tolerant search
# ---------------------------------------------------------------------------

def test_search_households_name_order_tolerant():
    row = {"avhhid": "136683", "sfhhname": "Jackson, William and Rebecca",
           "sfadvisor": "A", "previousadvisor": ""}

    def fake_query(sql, params=()):
        # Exact-substring pass ("%William Jackson%") misses; the all-tokens pass
        # ("%William%" AND "%Jackson%") hits.
        if "LIKE ? AND" in " ".join(sql.split()) or sql.count("LIKE ?") >= 2:
            return [row]
        return []

    with patch.object(syn, "query", side_effect=fake_query):
        res = syn.search_households("William Jackson")
    assert res and res[0]["avhhid"] == "136683"


# ---------------------------------------------------------------------------
# Ticket-data disambiguation — Salesforce ids + account numbers
# ---------------------------------------------------------------------------

def test_extract_sf_ids_from_lightning_url_and_bare():
    text = ("see https://allworth.lightning.force.com/lightning/r/account_setup__c/"
            "0015G00002YGtlVQAT/view and ref 0013k00002hOb7BAAS")
    ids = compute.extract_sf_ids(text)
    assert "0015G00002YGtlVQAT" in ids
    assert "0013k00002hOb7BAAS" in ids


def test_extract_named_accounts_pairs_name_and_account():
    text = ("William Jackson - IRA ending 2155 - $278,144.71 "
            "Lauren Kirkpatrick - IRA account ending 0077 - $359,618")
    na = {n["name"]: n["account"] for n in compute.extract_named_accounts(text)}
    assert na.get("William Jackson") == "2155"
    assert na.get("Lauren Kirkpatrick") == "0077"


def test_lookup_by_sfhhid_resolves_exact():
    row = {"avhhid": "169981", "sfhhname": "Kipling, Randy", "sfadvisor": "B", "previousadvisor": ""}
    with patch.object(syn, "query", return_value=[row]) as q:
        res = syn.lookup_by_sfhhid("0015G00002YGtlVQAT")
    assert res[0]["avhhid"] == "169981"
    assert q.call_args.args[1] == ("0015G00002YGtlVQAT",)


def test_search_by_name_account_disambiguates_same_surname():
    right = {"avhhid": "136683", "sfhhname": "Jackson, William and Rebecca",
             "sfadvisor": "A", "previousadvisor": ""}
    with patch.object(syn, "query", return_value=[right]) as q:
        res = syn.search_households_by_name_account("William Jackson", "2155")
    assert res[0]["avhhid"] == "136683"
    # name tokens + account suffix are all bound as params
    assert q.call_args.args[1] == ("%William%", "%Jackson%", "%2155")


def test_search_by_name_account_needs_both():
    assert syn.search_households_by_name_account("", "2155") == []
    assert syn.search_households_by_name_account("Jackson", "") == []


# ---------------------------------------------------------------------------
# Multi-client row building + de-dup (agent, with gather/LLM mocked)
# ---------------------------------------------------------------------------

def test_propose_dedupes_same_household():
    from nfbc import agent

    ticket = {"key": "AI-9999", "summary": "joint", "description": "Kirkpatrick, John and Vicki"}
    inv = {"238039": {"dim": {"avhhid": "238039", "sfhhname": "Kirkpatrick, John and Vicki",
                              "sfadvisor": "A"}, "flows": [], "adjustments": []}}
    # LLM emits two proposals that both resolve to the same household.
    proposals = [
        {"selected_avhhid": 238039, "adjustment_type": "Net New", "rationale": "John",
         "draft_reply": "", "confidence": 0.9},
        {"selected_avhhid": 238039, "adjustment_type": "Net New", "rationale": "Vicki",
         "draft_reply": "", "confidence": 0.9},
    ]
    with patch.object(agent, "_gather", return_value=(inv, [])), \
         patch.object(agent, "_call_llm", return_value=proposals):
        rows = agent.propose_for_ticket(ticket)
    assert len([r for r in rows if r.get("avhhid") == "238039"]) == 1


# ---------------------------------------------------------------------------
# Full confirm flow — attributed Jira comment (mock e2e)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from flask import Flask
    from nfbc.routes import bp

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(bp, url_prefix="/api/nfbc")
    return app.test_client()


def test_confirm_stamps_acting_user_into_comment(client):
    from nfbc import routes

    row = {
        "row_id": "AI-7141:27763", "ticket_key": "AI-7141", "avhhid": 27763,
        "period": "2026-05-31", "amount": 1000000.0, "multiplier": 1,
        "adjustment_type": "Account Processing Delay",
        "draft_reply": "An adjustment will be recorded to restore correct net flows.",
        "status": "proposed",
    }

    add_comment = MagicMock(return_value={"id": "10001"})
    with patch.object(routes.store, "get_proposal", return_value=row), \
         patch.object(routes.store, "set_status"), \
         patch.object(routes.store, "append_event"), \
         patch.object(routes.syn, "get_adjustments_for", return_value=[]), \
         patch.object(routes.syn, "insert_adjustment", return_value=1) as insert, \
         patch.object(routes.jira_client, "add_comment", add_comment), \
         patch.object(routes.jira_client, "transition_issue", return_value={"ok": True}):
        resp = client.post(
            "/api/nfbc/queue/AI-7141:27763/confirm",
            headers={"X-Ms-Client-Principal-Name": "nicholas.mckenzie@allworthfinancial.com"},
            json={},
        )

    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["ok"] is True
    # DB write happened with the row's numbers.
    insert.assert_called_once()
    assert insert.call_args.args[:4] == (27763, "2026-05-31", 1000000.0, "Account Processing Delay")
    # The Jira comment is stamped with the acting user, not the API-token owner.
    posted_body = add_comment.call_args.args[1]
    assert "Recorded by nicholas.mckenzie@allworthfinancial.com" in posted_body
    assert "An adjustment will be recorded" in posted_body


def test_confirm_rejects_missing_amount(client):
    from nfbc import routes

    row = {"row_id": "AI-1:1", "ticket_key": "AI-1", "avhhid": 27763,
           "period": "2026-05-31", "amount": None, "status": "proposed"}
    with patch.object(routes.store, "get_proposal", return_value=row):
        resp = client.post("/api/nfbc/queue/AI-1:1/confirm", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Connection hygiene — writes must stay transactional after the cache DDL
# ---------------------------------------------------------------------------

def test_new_conn_forces_transactional_autocommit():
    # The cache DDL runs in autocommit mode; pyodbc's ODBC pooling can hand that
    # connection back to a write(), whose commit() would then fail with
    # "no corresponding transaction" (Synapse 111214). _new_conn must normalize
    # every connection back to autocommit=False.
    fake = MagicMock()
    with patch.object(syn.pyodbc, "connect", return_value=fake):
        conn = syn._new_conn()
    assert conn is fake
    assert fake.autocommit is False

