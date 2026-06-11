"""Anthropic client singleton. None when no API key — the app then runs in
deterministic fallback mode (demo never dies on stage)."""

import os

from anthropic import AsyncAnthropic

from allworth_api import config as _config  # noqa: F401  (loads .env before the key is read)

CHAT_MODEL = "claude-opus-4-7"
EXTRACT_MODEL = "claude-haiku-4-5"

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
client = AsyncAnthropic(api_key=api_key) if api_key else None
