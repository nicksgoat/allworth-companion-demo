"""Content-addressed deterministic projection cache."""

from collections import OrderedDict
from hashlib import sha256
import json
import os
from threading import RLock

from planengine.engine import run_projection
from planengine.models import Projection

# Redis is an optional distributed cache. When the package (or REDIS_URL) is
# absent the service falls back to the in-process LRU cache below.
try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - optional dependency
    Redis = None  # type: ignore[assignment]

    class RedisError(Exception):  # type: ignore[no-redef]
        pass


class ProjectionService:
    def __init__(self, max_entries: int = 512):
        self.max_entries = max_entries
        self._cache = OrderedDict()
        self._lock = RLock()
        redis_url = (os.getenv("REDIS_URL") or "").strip()
        self.redis = Redis.from_url(redis_url, decode_responses=True) if (redis_url and Redis) else None

    @staticmethod
    def key(facts, tracing: bool = False) -> str:
        payload = json.dumps(facts.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return sha256(f"engine-v1|tables-2026|trace={tracing}|{payload}".encode()).hexdigest()

    def project(self, facts, tracing: bool = False):
        key = self.key(facts, tracing)
        if self.redis:
            try:
                cached = self.redis.get(f"projection:{key}")
                if cached: return Projection.model_validate_json(cached)
            except RedisError:
                pass
        with self._lock:
            if key in self._cache:
                result = self._cache.pop(key); self._cache[key] = result
                return result.model_copy(deep=True)
        result = run_projection(facts, trace=tracing)
        if self.redis:
            try: self.redis.setex(f"projection:{key}", 3600, result.model_dump_json())
            except RedisError: pass
        with self._lock:
            self._cache[key] = result
            while len(self._cache) > self.max_entries: self._cache.popitem(last=False)
        return result.model_copy(deep=True)

    def clear(self) -> None:
        """Purge all cached projections (used for privacy deletion and deploys)."""
        with self._lock:
            self._cache.clear()
        if self.redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = self.redis.scan(cursor=cursor, match="projection:*", count=500)
                    if keys: self.redis.delete(*keys)
                    if cursor == 0: break
            except RedisError:
                pass


projection_service = ProjectionService()
