"""Upload + ingestion endpoints."""

from __future__ import annotations

from flask import Blueprint, request

from investments.config import settings
from investments.routers._helpers import api_error, to_summary
from investments.services.ingest import IngestError, parse_tamarac
from investments.services.store import store

bp = Blueprint("upload", __name__, url_prefix="/api")


@bp.post("/upload")
def upload() -> dict:
    file = request.files.get("file")
    if file is None:
        raise api_error(400, "A file upload named 'file' is required.")
    content = file.read()
    if len(content) > settings.max_upload_bytes:
        raise api_error(413, "File exceeds the maximum upload size.")
    if not content:
        raise api_error(400, "The uploaded file is empty.")

    try:
        bonds = parse_tamarac(content, file.filename or "upload.csv")
    except IngestError as exc:
        raise api_error(400, str(exc)) from exc

    name = (file.filename or "Portfolio").rsplit(".", 1)[0]
    portfolio = store.add(name=name, bonds=bonds, source_filename=file.filename or "upload.csv")
    return {
        "portfolio": to_summary(portfolio),
        "message": f"Parsed {len(bonds)} fixed-income holdings across "
        f"{len(portfolio.account_ids)} account(s).",
    }
