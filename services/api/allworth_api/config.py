"""Paths and environment for the Allworth demo backend.

Importing this module loads .env, so any module that reads environment
variables (e.g. the Anthropic client) must import config first.
"""

from pathlib import Path

from dotenv import load_dotenv

API_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = API_DIR / "data"
FALLBACKS_DIR = API_DIR / "fallbacks"
MEMORY_DIR = API_DIR / "memory"

load_dotenv(API_DIR / ".env")
