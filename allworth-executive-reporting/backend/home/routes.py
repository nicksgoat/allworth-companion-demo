"""Flask Blueprint for the team hub — mount at /home."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, abort, render_template_string, request, send_file

bp = Blueprint(
    "home",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"
# Share the Jarvis logo so we don't duplicate binary assets.
_LOGO_PATH = Path(__file__).parent.parent / "jarvis" / "static" / "logo.png"


@bp.get("/")
def index():
    # Read the template directly instead of using render_template("index.html"),
    # which collides with Jarvis's template of the same name in Flask's Jinja loader.
    html = _TEMPLATE_PATH.read_text(encoding="utf-8")

    # Best-effort per-user filtering: hide cards/nav for tools the signed-in
    # user lacks. Resolve identity from the platform (Easy Auth) or an explicit
    # header; if we can't (e.g. local dev), pass null so the hub shows all
    # tools (fail-open — the tool pages themselves still enforce access).
    allowed_tools = _resolve_allowed_tools()
    allowed_json = "null" if allowed_tools is None else json.dumps(sorted(allowed_tools))

    return render_template_string(html, base_url="/home", allowed_tools_json=allowed_json)


def _resolve_allowed_tools() -> set[str] | None:
    email = (
        request.headers.get("x-ms-client-principal-name")
        or request.headers.get("X-Ms-Client-Principal-Name")
        or request.headers.get("X-User-Email")
        or request.headers.get("x-user-email")
    )
    if not email:
        return None
    try:
        from admin import store as admin_store

        if not admin_store.enforcement_enabled():
            return None  # enforcement staged off — show everything
        info = admin_store.effective_for(email)
        if info.get("all_access"):
            return None  # all-access users see everything
        return set(info.get("effective_tools", []))
    except Exception:
        return None


@bp.get("/logo.png")
def logo():
    if not _LOGO_PATH.exists():
        abort(404)
    return send_file(_LOGO_PATH, mimetype="image/png")


