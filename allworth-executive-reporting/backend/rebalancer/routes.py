"""Mock Rebalancer routes — tax-transition what-if rebalancing.

Read-only against the warehouse; produces a proposed trade list but never
submits trades anywhere. Client portal roles are blocked (advisor tooling).
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from rebalancer import service

bp = Blueprint("rebalancer", __name__)
logger = logging.getLogger(__name__)


def _roles() -> set[str]:
    claims = request.environ.get("user.claims") or {}
    roles = claims.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    return {str(role).lower() for role in roles}


def _is_client() -> bool:
    return bool(_roles() & {"client", "portal_client", "planengine.client"})


@bp.before_request
def _block_clients():
    if _is_client():
        return jsonify({"error": "not available for client accounts"}), 403
    return None


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "module": "rebalancer", "mode": "mock"})


@bp.get("/models")
def models():
    try:
        return jsonify(service.list_models())
    except Exception as exc:  # pragma: no cover - warehouse connectivity
        logger.error("rebalancer models fetch failed: %s", exc)
        return jsonify({"error": str(exc)}), 502


@bp.get("/models/<path:model_name>")
def model_details(model_name: str):
    try:
        return jsonify(service.get_model_details(model_name))
    except Exception as exc:  # pragma: no cover - warehouse connectivity
        logger.error("rebalancer model details failed: %s", exc)
        return jsonify({"error": str(exc)}), 502


@bp.get("/account/<account_number>")
def account(account_number: str):
    try:
        resolved = service.resolve_account(account_number)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:  # pragma: no cover - warehouse connectivity
        logger.error("rebalancer account resolve failed: %s", exc)
        return jsonify({"error": str(exc)}), 502
    return jsonify(resolved)


@bp.get("/portfolio/<upload_account_id>")
def portfolio(upload_account_id: str):
    try:
        holdings = service.get_portfolio(upload_account_id)
    except Exception as exc:  # pragma: no cover - warehouse connectivity
        logger.error("rebalancer portfolio fetch failed: %s", exc)
        return jsonify({"error": str(exc)}), 502
    return jsonify({"upload_account_id": upload_account_id, "holdings": holdings})


@bp.post("/optimize")
def optimize():
    data = request.get_json(silent=True) or {}

    required = ["short_term_tax_rate", "long_term_tax_rate"]
    missing = [field for field in required if field not in data]
    if not data.get("target_allocation") and not (data.get("model") and data.get("allocation")):
        missing.append("target_allocation or model+allocation")
    if not data.get("upload_account_id") and not data.get("account_number"):
        missing.append("upload_account_id or account_number")
    if missing:
        return jsonify({"error": f"missing required field(s): {', '.join(missing)}"}), 400

    try:
        if not data.get("target_allocation"):
            resolved_name = service.resolve_target_name(
                str(data["model"]), str(data["allocation"])
            )
            if not resolved_name:
                return jsonify({"error": "no allocation model found for that model/allocation"}), 422
            data["target_allocation"] = resolved_name

        if not data.get("upload_account_id"):
            resolved = service.resolve_account(str(data["account_number"]))
            if resolved.get("below_minimum"):
                return jsonify({"error": "account below minimum value for rebalancing"}), 422
            data["upload_account_id"] = resolved["upload_account_id"]

        results = service.run_optimization(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        logger.error("rebalancer optimization failed: %s", exc)
        return jsonify({"error": str(exc)}), 500

    return jsonify({"success": True, "results": results})
