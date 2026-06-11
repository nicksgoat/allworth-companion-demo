"""File-backed client profile store: immutable seed + mutable runtime overlay."""

import json
import random
import string
import time
from pathlib import Path

from allworth_api.config import MEMORY_DIR

BASE36 = string.digits + string.ascii_lowercase


def seed_path(client_id: str) -> Path:
    return MEMORY_DIR / f"{client_id}.seed.json"


def runtime_path(client_id: str) -> Path:
    return MEMORY_DIR / f"{client_id}.runtime.json"


def new_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{''.join(random.choices(BASE36, k=4))}"


def load_profile(client_id: str) -> dict:
    runtime, seed_file = runtime_path(client_id), seed_path(client_id)
    if runtime.exists():
        profile = json.loads(runtime.read_text())
    elif seed_file.exists():
        profile = json.loads(seed_file.read_text())
    else:
        profile = {"clientId": client_id, "facts": [], "episodes": []}
    # Seed facts predate fact ids; assign stable ids on first load.
    assigned = False
    for i, f in enumerate(profile["facts"]):
        if not f.get("id"):
            f["id"] = f"fact_seed_{i}"
            assigned = True
    if assigned or not runtime.exists():
        save_profile(client_id, profile)
    return profile


def save_profile(client_id: str, profile: dict) -> None:
    runtime_path(client_id).write_text(json.dumps(profile, indent=2))
