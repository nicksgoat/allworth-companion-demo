"""Lightweight response quality signal storage."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from allworth_api.config import API_DIR
from allworth_api.core.formatting import iso_now
from allworth_api.core.observability import hash_household_id

FEEDBACK_PATH = Path(API_DIR) / "feedback.log"
logger = logging.getLogger("allworth_api.feedback")


def feedback_log_path() -> Path:
    return Path(os.environ.get("FEEDBACK_LOG_PATH", FEEDBACK_PATH))


def record_response_feedback(
    *,
    client_id: str,
    conversation_id: str,
    message_id: str,
    rating: str,
    sources: list[str] | None = None,
    tool_calls: list[str] | None = None,
    suggestions: list[str] | None = None,
    answer_preview: str | None = None,
    quality: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    quality = quality or {}
    entry = {
        "ts": iso_now(),
        "request_id": request_id,
        "client_hash": hash_household_id(client_id),
        "conversation_id": conversation_id,
        "message_id": message_id,
        "rating": rating,
        "sources": sources or [],
        "tool_calls_used": tool_calls or [],
        "suggestions": suggestions or [],
        "answer_preview": (answer_preview or "")[:500],
        "quality": {
            "vision_score": quality.get("vision_score"),
            "missing": quality.get("missing") or [],
            "safety_flags": quality.get("safety_flags") or [],
        },
    }
    path = feedback_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    logger.info(
        json.dumps(
            {
                "event": "chat_feedback",
                "request_id": request_id,
                "client_hash": entry["client_hash"],
                "conversation_id": conversation_id,
                "message_id": message_id,
                "rating": rating,
                "source_count": len(entry["sources"]),
                "tool_count": len(entry["tool_calls_used"]),
                "suggestion_count": len(entry["suggestions"]),
                "vision_score": entry["quality"]["vision_score"],
                "safety_flags": entry["quality"]["safety_flags"],
            },
            separators=(",", ":"),
        )
    )
    return {"ok": True, "feedback": entry}
