"""SSE wire encoding. The separators and ensure_ascii flags are part of the
byte-level API contract — do not touch."""

import json


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'), ensure_ascii=False)}\n\n"
