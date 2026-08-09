"""Background warm-up + DB keep-alive.

Eliminates the cold-load stall on the Bond Ladder landing page: the first
``get_bond_ladder`` call after a container start costs ~11s (Synapse connect +
two scans). A daemon thread pre-populates the cache on startup, rebuilds it
before its 30-minute TTL expires, and periodically pings the pool so the next
real request does not pay the ~2s reconnect after idle.
"""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import text

logger = logging.getLogger("app.warmup")

_KEEPALIVE_INTERVAL = 240          # 4 min: exercise a pooled connection
_CACHE_REFRESH_INTERVAL = 20 * 60  # 20 min: rebuild before the 30-min ladder TTL

_started = False
_lock = threading.Lock()


def _loop() -> None:
    from investments.db import get_session_factory
    from investments.services import bond_ladder

    last_refresh = 0.0
    while True:
        try:
            session = get_session_factory()()
            try:
                now = time.monotonic()
                if now - last_refresh >= _CACHE_REFRESH_INTERVAL:
                    bond_ladder.invalidate_cache()
                    result = bond_ladder.get_bond_ladder(session)
                    last_refresh = now
                    logger.info("bond-ladder cache warmed (%d accounts)", len(result.accounts))
                else:
                    session.execute(text("SELECT 1"))
            finally:
                session.close()
        except Exception as exc:  # never let the warmer take down the app
            logger.warning("warm-up/keep-alive skipped: %s", exc)
        time.sleep(_KEEPALIVE_INTERVAL)


def start() -> None:
    """Start the warm-up daemon once, if the database is configured."""
    global _started
    with _lock:
        if _started:
            return
        try:
            from investments.db import resolve_database_url

            resolve_database_url()
        except Exception:
            logger.info("Database not configured; skipping bond-ladder warm-up.")
            return
        threading.Thread(target=_loop, name="bond-ladder-warmup", daemon=True).start()
        _started = True
        _started = True
        logger.info("bond-ladder warm-up thread started.")
