"""Claude agent service — proposes NFBC adjustments; code finalizes the numbers.

For each ticket: gather candidate households from Synapse, ask Claude (forced
tool-use, structured output) to resolve household(s), classify, and draft a
reply, then hand each proposal to compute.finalize() which OWNS the dollar
amount, period, and validation.

Falls back to a deterministic proposal when ANTHROPIC_API_KEY is unset, so the
queue still works (and tests run) without the LLM.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from nfbc import compute, synapse_nfbc as syn

logger = logging.getLogger(__name__)

# LLM provider — auto-detected from whichever API key is present; override with
# NFBC_LLM_PROVIDER=openai|anthropic. The agent's reasoning is provider-agnostic;
# only the SDK call + tool-schema wrapper differ.
_PROVIDER = os.getenv("NFBC_LLM_PROVIDER", "").strip().lower()
_ANTHROPIC_MODEL = os.getenv("NFBC_CLAUDE_MODEL", "claude-opus-4-8")
_OPENAI_MODEL = os.getenv("NFBC_OPENAI_MODEL", "gpt-4.1")
_MAX_CANDIDATES = 6
# Per-call timeout (seconds). SDK defaults (up to 600s with retries) can stall
# the whole queue build for minutes per ticket when egress is blocked.
_LLM_TIMEOUT = float(os.getenv("NFBC_LLM_TIMEOUT_SECONDS",
                               os.getenv("NFBC_CLAUDE_TIMEOUT_SECONDS", "60")))
# After this many consecutive failures, stop calling the LLM for the rest of the
# build and use the deterministic fallback (egress blocked / bad key / outage).
_LLM_TRIP_AFTER = 3
_llm_consecutive_failures = 0
_PROMPT_DIR = Path(__file__).parent / "prompts"

_PROPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "adjustments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "resolved": {"type": "boolean"},
                    "selected_avhhid": {
                        "type": ["integer", "string", "null"],
                        "description": "Choose ONLY from the candidate avhhids provided.",
                    },
                    "adjustment_type": {"type": "string"},
                    "proposed_amount": {
                        "type": ["number", "null"],
                        "description": "Sanity-check only; code recomputes the authoritative amount.",
                    },
                    "proposed_period": {"type": ["string", "null"]},
                    "rationale": {"type": "string"},
                    "draft_reply": {"type": "string"},
                    "confidence": {"type": "number"},
                    "needs_human_flags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["resolved", "selected_avhhid", "adjustment_type",
                             "rationale", "draft_reply", "confidence"],
            },
        }
    },
    "required": ["adjustments"],
}

# Anthropic tool-use shape.
_PROPOSE_TOOL = {
    "name": "propose_adjustments",
    "description": "Return the proposed NFBC adjustment(s) for this ticket.",
    "input_schema": _PROPOSE_SCHEMA,
}

# OpenAI function-calling shape (same JSON schema, different wrapper).
_OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_adjustments",
        "description": "Return the proposed NFBC adjustment(s) for this ticket.",
        "parameters": _PROPOSE_SCHEMA,
    },
}


def _load(name: str) -> str:
    p = _PROMPT_DIR / name
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


_SYSTEM_INSTRUCTIONS = _load("system_prompt.md")
_PLAYBOOK = _load("playbook.md")

_anthropic_client = None
_anthropic_resolved = False
# OpenAI client is resolved lazily but NOT cached-on-failure: the key may live in
# Key Vault and access can be granted while the app is running, so a failed
# lookup is retried after a short backoff instead of disabling OpenAI until the
# next restart. Only a successful client is cached.
_openai_client = None
_openai_is_azure = False
_openai_last_attempt = 0.0
_OPENAI_RETRY_SECS = float(os.getenv("NFBC_OPENAI_RETRY_SECONDS", "30"))


def _provider() -> str:
    """Which LLM to use: explicit override, else whichever client can be built
    (env var or Key Vault). Constructing the client is cached, so this is cheap
    after the first call."""
    if _PROVIDER in ("openai", "anthropic"):
        return _PROVIDER
    if _openai() is not None:
        return "openai"
    if _anthropic() is not None:
        return "anthropic"
    return "none"


# Candidate KV secret names (override the key name with NFBC_OPENAI_KV_SECRET).
# Azure OpenAI stores three secrets — key + endpoint + api-version. When an
# endpoint resolves, the AzureOpenAI client is used (addressed by deployment
# name); otherwise the public OpenAI client (key only).
_OPENAI_KV_NAMES = [
    os.getenv("NFBC_OPENAI_KV_SECRET", ""),
    "azure-openai-api-key",
    "openaikey", "openai-api-key", "openai-key", "openaiapikey", "OpenAIKey",
]
_AZURE_ENDPOINT_KV_NAMES = [
    os.getenv("NFBC_AZURE_OPENAI_ENDPOINT_KV_SECRET", ""),
    "azure-openai-endpoint",
]
_AZURE_APIVERSION_KV_NAMES = [
    os.getenv("NFBC_AZURE_OPENAI_APIVERSION_KV_SECRET", ""),
    "azure-openai-apiversion", "azure-openai-api-version",
]
# Azure addresses a model by its DEPLOYMENT name, not the model id.
_AZURE_DEPLOYMENT = os.getenv("NFBC_AZURE_OPENAI_DEPLOYMENT", _OPENAI_MODEL)
_DEFAULT_AZURE_APIVERSION = "2024-10-21"


def _resolve_openai_key(prefer_azure: bool = False) -> str | None:
    """OpenAI/Azure OpenAI key from env first, else Key Vault (allworthsynapse).

    When ``prefer_azure`` (an Azure endpoint is configured) the Azure key wins so
    a stale public ``OPENAI_API_KEY`` can't be handed to the AzureOpenAI client.
    """
    env_order = (("AZURE_OPENAI_API_KEY", "OPENAI_API_KEY") if prefer_azure
                 else ("OPENAI_API_KEY", "AZURE_OPENAI_API_KEY"))
    for name in env_order:
        val = os.getenv(name)
        if val:
            return val
    try:
        from nfbc import kv
        return kv.get_secret(_OPENAI_KV_NAMES)
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("OpenAI KV lookup unavailable: %s", exc)
        return None


def _resolve_azure_endpoint() -> str | None:
    """Azure OpenAI endpoint from env first, else Key Vault. Its presence is what
    selects the AzureOpenAI client over the public OpenAI client."""
    env = os.getenv("AZURE_OPENAI_ENDPOINT")
    if env:
        return env
    try:
        from nfbc import kv
        return kv.get_secret(_AZURE_ENDPOINT_KV_NAMES)
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("Azure OpenAI endpoint KV lookup unavailable: %s", exc)
        return None


def _resolve_azure_api_version() -> str:
    """Azure OpenAI api-version from env, else Key Vault, else a GA default."""
    env = os.getenv("AZURE_OPENAI_API_VERSION")
    if env:
        return env
    try:
        from nfbc import kv
        val = kv.get_secret(_AZURE_APIVERSION_KV_NAMES)
    except Exception:
        val = None
    return val or _DEFAULT_AZURE_APIVERSION


def _openai_model_id() -> str:
    """Deployment name for Azure, model id for public OpenAI."""
    return _AZURE_DEPLOYMENT if _openai_is_azure else _OPENAI_MODEL


def _anthropic():
    """Lazy Anthropic client; None if SDK or API key unavailable."""
    global _anthropic_client, _anthropic_resolved
    if _anthropic_resolved:
        return _anthropic_client
    _anthropic_resolved = True
    if not os.getenv("ANTHROPIC_API_KEY"):
        _anthropic_client = None
        return None
    try:
        from anthropic import Anthropic
        _anthropic_client = Anthropic(timeout=_LLM_TIMEOUT, max_retries=1)
    except Exception as exc:
        logger.warning("Anthropic SDK unavailable (%s) — using fallback", exc)
        _anthropic_client = None
    return _anthropic_client


def _openai():
    """Lazy OpenAI client; None if SDK or API key unavailable (env or Key Vault).

    If an Azure OpenAI endpoint resolves (env or Key Vault) an AzureOpenAI client
    is built and addressed by deployment name; otherwise the public OpenAI
    client. Retries a failed lookup after _OPENAI_RETRY_SECS so a Key Vault
    access grant applied while the app is running is picked up without a restart.
    """
    global _openai_client, _openai_last_attempt, _openai_is_azure
    if _openai_client is not None:
        return _openai_client
    now = time.time()
    if now - _openai_last_attempt < _OPENAI_RETRY_SECS:
        return None  # backoff — avoid hammering Key Vault on every ticket
    _openai_last_attempt = now
    endpoint = _resolve_azure_endpoint()
    api_key = _resolve_openai_key(prefer_azure=bool(endpoint))
    if not api_key:
        return None
    try:
        if endpoint:
            from openai import AzureOpenAI
            _openai_client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=_resolve_azure_api_version(),
                timeout=_LLM_TIMEOUT,
                max_retries=1,
            )
            _openai_is_azure = True
        else:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=api_key, timeout=_LLM_TIMEOUT, max_retries=1)
            _openai_is_azure = False
    except Exception as exc:
        logger.warning("OpenAI SDK unavailable (%s) — using fallback", exc)
        _openai_client = None
    return _openai_client


# ── candidate gathering ──────────────────────────────────────────────────────


def _gather(ticket: dict) -> tuple[dict[str, dict], list[dict]]:
    """Resolve candidate households and investigate them.

    Returns (investigations keyed by str(avhhid), parsed_clients).
    """
    investigations: dict[str, dict] = {}
    parsed_clients = compute.parse_client_lines(ticket.get("description", "") or "")
    reporter = (ticket.get("reporter") or "").strip()
    ticket_text = f"{ticket.get('summary','')} {ticket.get('description','')}"

    seen: set[str] = set()

    def _consider(rows: list[dict], limit: int | None = None):
        """Investigate up to ``limit`` new households from ``rows`` (bounded by
        _MAX_CANDIDATES overall). The per-term limit stops one broad surname
        match from crowding out the ticket's other named clients."""
        added = 0
        for r in rows:
            avhhid = str(r.get("avhhid"))
            if not avhhid or avhhid in seen or len(investigations) >= _MAX_CANDIDATES:
                continue
            if limit is not None and added >= limit:
                return
            seen.add(avhhid)
            try:
                investigations[avhhid] = syn.investigate_household(avhhid)
                added += 1
            except Exception as exc:
                logger.warning("investigate_household(%s) failed: %s", avhhid, exc)

    # 0. Precise disambiguators from ticket data — Salesforce record ids and
    #    name+account-number pairs pin the EXACT household when a name is shared
    #    by several (e.g. three "William Jackson" households). Run these first.
    for sfid in compute.extract_sf_ids(ticket_text):
        if len(investigations) >= _MAX_CANDIDATES:
            break
        _consider(syn.lookup_by_sfhhid(sfid), limit=1)
    for na in compute.extract_named_accounts(ticket_text):
        if len(investigations) >= _MAX_CANDIDATES:
            break
        _consider(syn.search_households_by_name_account(na["name"], na["account"]), limit=1)

    # 1. Explicit parsed clients ("LastName, FirstName" in the body).
    for client in parsed_clients:
        if len(investigations) >= _MAX_CANDIDATES:
            break
        results = syn.search_households(client["name"])
        if not results:
            results = syn.search_households(client["name"].split(",")[0].strip())
        _consider(results, limit=2)

    # 2. Ranked candidates, highest confidence first, in NAME mode. This finds
    #    both named clients AND the reporter's OWN household (advisor-self
    #    tickets, e.g. "outflow under my name"). Each term is capped so a common
    #    surname can't fill every slot before the other named clients are seen.
    for cand in sorted(compute.extract_candidates(ticket), key=lambda c: -c["confidence"]):
        if len(investigations) >= _MAX_CANDIDATES:
            break
        _consider(syn.search_households(cand["term"]), limit=2)

    # 3. Last resort: nothing resolved by name and the reporter is an advisor —
    #    pull their book (bounded). Rare: most advisor tickets name the client.
    if not investigations and reporter and syn.is_advisor(reporter):
        _consider(syn.search_households(reporter, search_advisors=True))

    return investigations, parsed_clients


def _parsed_amount_for(dim: dict, parsed_clients: list[dict]) -> float | None:
    """Match a household to a parsed client amount by last-name token."""
    name = (dim.get("sfhhname") or "").lower()
    if not name:
        return None
    best = None
    for c in parsed_clients:
        if c.get("amount") is None:
            continue
        last = c["name"].split(",")[0].strip().lower()
        if last and last in name:
            best = c["amount"]
    if best is None and len(parsed_clients) == 1 and parsed_clients[0].get("amount"):
        best = parsed_clients[0]["amount"]
    return best


# ── Claude call ───────────────────────────────────────────────────────────────


def _candidate_context(investigations: dict[str, dict]) -> str:
    parts = []
    for avhhid, inv in investigations.items():
        dim = inv.get("dim") or {}
        flows = inv.get("flows") or []
        adjs = inv.get("adjustments") or []
        flow_lines = "; ".join(
            f"{f['reportingperiod']}: in={f.get('inflows')}, out={f.get('outflows')}, net={f.get('net_flows')}"
            for f in flows[-6:]
        ) or "no recent flows"
        adj_lines = "; ".join(
            f"{a['reportingperiod']}=${a.get('flow_adjustment')}" for a in adjs
        ) or "none"
        parts.append(
            f"- avhhid {avhhid}: {dim.get('sfhhname')} | advisor {dim.get('sfadvisor')}"
            f" | previous {dim.get('previousadvisor') or '—'}\n"
            f"    recent flows: {flow_lines}\n"
            f"    existing adjustments: {adj_lines}"
        )
    return "\n".join(parts) if parts else "(no candidate households resolved)"


def _build_user_content(ticket: dict, investigations: dict[str, dict],
                        parsed_clients: list[dict]) -> str:
    comments = "\n".join(f"- {c['author']}: {c['body']}" for c in ticket.get("comments", []))
    return (
        f"TICKET {ticket.get('key')}\n"
        f"Summary: {ticket.get('summary')}\n"
        f"Reporter: {ticket.get('reporter')}\n"
        f"Description:\n{ticket.get('description')}\n"
        f"Comments:\n{comments or '(none)'}\n\n"
        f"Parsed client/amount hints: {json.dumps(parsed_clients)}\n\n"
        f"CANDIDATE HOUSEHOLDS (choose selected_avhhid only from these):\n"
        f"{_candidate_context(investigations)}\n\n"
        f"Return proposal(s) via the propose_adjustments tool."
    )


def _call_anthropic(client, user_content: str) -> list[dict] | None:
    resp = client.messages.create(
        model=_ANTHROPIC_MODEL,
        max_tokens=2000,
        system=[
            {"type": "text", "text": _SYSTEM_INSTRUCTIONS},
            {"type": "text", "text": _PLAYBOOK, "cache_control": {"type": "ephemeral"}},
        ],
        tools=[_PROPOSE_TOOL],
        tool_choice={"type": "tool", "name": "propose_adjustments"},
        messages=[{"role": "user", "content": user_content}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "propose_adjustments":
            return block.input.get("adjustments", [])
    return None


def _call_openai(client, user_content: str) -> list[dict] | None:
    resp = client.chat.completions.create(
        model=_openai_model_id(),
        messages=[
            {"role": "system", "content": f"{_SYSTEM_INSTRUCTIONS}\n\n{_PLAYBOOK}"},
            {"role": "user", "content": user_content},
        ],
        tools=[_OPENAI_TOOL],
        tool_choice={"type": "function", "function": {"name": "propose_adjustments"}},
    )
    msg = resp.choices[0].message
    for call in (msg.tool_calls or []):
        if call.function.name == "propose_adjustments":
            args = json.loads(call.function.arguments or "{}")
            return args.get("adjustments", [])
    return None


def _call_llm(ticket: dict, investigations: dict[str, dict],
              parsed_clients: list[dict]) -> list[dict] | None:
    """Provider-agnostic proposal call. None -> caller uses deterministic fallback."""
    global _llm_consecutive_failures
    if _llm_consecutive_failures >= _LLM_TRIP_AFTER:
        return None  # circuit tripped — deterministic fallback for the rest
    provider = _provider()
    client = _openai() if provider == "openai" else _anthropic() if provider == "anthropic" else None
    if client is None:
        return None

    user_content = _build_user_content(ticket, investigations, parsed_clients)
    try:
        result = (_call_openai(client, user_content) if provider == "openai"
                  else _call_anthropic(client, user_content))
    except Exception as exc:
        _llm_consecutive_failures += 1
        logger.warning("%s call failed for %s (%d consecutive): %s — using fallback",
                       provider, ticket.get("key"), _llm_consecutive_failures, exc)
        return None

    _llm_consecutive_failures = 0
    return result


def _fallback_proposals(investigations: dict[str, dict]) -> list[dict]:
    """Deterministic proposal when the LLM is unavailable: top candidate only."""
    if not investigations:
        return [{"resolved": False, "selected_avhhid": None, "adjustment_type": "Net New",
                 "rationale": "No candidate household resolved (LLM unavailable).",
                 "draft_reply": "", "confidence": 0.0,
                 "needs_human_flags": ["LLM unavailable; resolved by heuristics only."]}]
    avhhid = next(iter(investigations))
    return [{"resolved": True, "selected_avhhid": avhhid, "adjustment_type": "Net New",
             "rationale": "Heuristic match (LLM unavailable).", "draft_reply": "",
             "confidence": 0.3,
             "needs_human_flags": ["LLM unavailable; verify household + reply text."]}]


# ── public entrypoint ─────────────────────────────────────────────────────────


def diagnostics() -> dict:
    """Surface the active LLM provider/model for /health — shows whether the
    agent is actually reasoning or falling back to heuristics."""
    # Resolve the provider FIRST — that triggers the (cached) key/KV lookups, so
    # kv_error below reflects this run rather than a stale prior value.
    prov = _provider()
    try:
        from nfbc import kv
        kv_err = kv.last_error()
        vault = kv.vault_name()
    except Exception:
        kv_err, vault = None, None
    return {
        "provider": prov,
        "model": (_openai_model_id() if prov == "openai"
                  else _ANTHROPIC_MODEL if prov == "anthropic" else None),
        "openai_key": _openai() is not None,
        "openai_flavor": ("azure" if _openai_is_azure else "openai") if prov == "openai" else None,
        "openai_key_source": ("env" if (os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))
                              else "keyvault" if _openai() is not None else None),
        "anthropic_key": _anthropic() is not None,
        "key_vault": vault,
        "kv_error": kv_err,
        "consecutive_failures": _llm_consecutive_failures,
    }


def propose_for_ticket(ticket: dict) -> list[dict]:
    """Return a list of finalized queue rows for one ticket (code owns numbers)."""
    investigations, parsed_clients = _gather(ticket)

    proposals = _call_llm(ticket, investigations, parsed_clients)
    if proposals is None:
        proposals = _fallback_proposals(investigations)

    ticket_text = f"{ticket.get('summary','')} {ticket.get('description','')}"
    rows: list[dict] = []
    resolved_seen: set[str] = set()
    for prop in proposals:
        sel = prop.get("selected_avhhid")
        inv = investigations.get(str(sel)) if sel is not None else None

        if inv is None:
            # Unresolved — surface a row that needs human attention, no numbers.
            rows.append({
                "ticket_key": ticket.get("key"),
                "ticket_summary": ticket.get("summary"),
                "ticket_status": ticket.get("status"),
                "row_id": f"{ticket.get('key')}:unresolved:{len(rows)}",
                "avhhid": None, "household": None, "advisor": None,
                "period": None, "amount": None, "multiplier": 1,
                "adjustment_type": prop.get("adjustment_type") or "Net New",
                "rationale": prop.get("rationale") or "Household not resolved.",
                "draft_reply": prop.get("draft_reply") or "",
                "confidence": prop.get("confidence"),
                "findings": [],
                "computed_vs_claude": {"claude_amount": prop.get("proposed_amount"), "code_amount": None},
                "needs_human_flags": (prop.get("needs_human_flags") or []) + ["No household resolved."],
                "status": "needs_review",
            })
            continue

        # One row per household: on a joint/multi-name ticket the LLM may emit
        # several proposals that resolve to the same household — keep the first.
        if str(sel) in resolved_seen:
            continue
        resolved_seen.add(str(sel))

        parsed_amount = _parsed_amount_for(inv.get("dim") or {}, parsed_clients)
        final = compute.finalize(prop, inv, ticket, parsed_amount=parsed_amount)
        final.update({
            "ticket_key": ticket.get("key"),
            "ticket_summary": ticket.get("summary"),
            "ticket_status": ticket.get("status"),
            "row_id": f"{ticket.get('key')}:{final.get('avhhid')}",
            "status": "proposed",
        })
        # carry the candidate flows for the detail view
        final["flows"] = inv.get("flows") or []
        final["existing_adjustments"] = inv.get("adjustments") or []
        rows.append(final)

    return rows
