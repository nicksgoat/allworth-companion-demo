"""
Async utilities for Tax Tools module - Stateless, scalable architecture

Provides:
- ShardedTTLCache: High-concurrency cache with TTL expiration and LRU eviction
- TTLCache: Thread-safe caching with TTL expiration (legacy, uses ShardedTTLCache)
- RequestQueue: Backpressure-aware request queue for optimization requests
- Dedicated optimization executor isolated from blocking I/O
- ThreadPoolExecutor: For blocking I/O operations
- Async helpers for parallel I/O operations
- Shared file storage helpers for multi-instance scaling
- Metrics collection for monitoring at scale
"""

import os
import asyncio
import logging
import time
import hashlib
import threading
from datetime import datetime
from threading import Lock, RLock, Semaphore, Condition, Event, Thread
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Optional, Callable, TypeVar, Dict, List, Tuple
from functools import wraps
from dataclasses import dataclass, field
from queue import Queue, Empty, Full
import multiprocessing

logger = logging.getLogger(__name__)


# ============================================================================
# SCALABILITY CONFIGURATION
# ============================================================================

@dataclass
class ScalabilityConfig:
    """Configuration for scalability parameters - tunable for different deployments."""
    
    # Cache settings
    cache_shards: int = 16  # Number of lock shards for cache (power of 2 recommended)
    cache_max_size_per_shard: int = 10000  # Max entries per shard before LRU eviction
    cache_cleanup_interval: int = 60  # Seconds between background cleanup
    
    # Request queue settings
    max_concurrent_optimizations: int = 50  # Max simultaneous optimizations
    max_queued_requests: int = 500  # Max requests waiting in queue
    request_timeout: float = 120.0  # Max seconds to wait for queue slot
    
    # Executor settings
    max_optimization_workers: int = 8  # Max optimization thread workers
    max_io_workers: int = 40  # Max thread pool workers
    
    # Memory management
    gc_threshold_mb: int = 1000  # Trigger GC when heap exceeds this
    
    @classmethod
    def for_load(cls, expected_users: int) -> 'ScalabilityConfig':
        """Get configuration tuned for expected concurrent users."""
        if expected_users <= 100:
            return cls()  # Default config
        elif expected_users <= 500:
            return cls(
                cache_shards=32,
                cache_max_size_per_shard=5000,
                max_concurrent_optimizations=100,
                max_queued_requests=1000,
                max_optimization_workers=12,
                max_io_workers=60,
            )
        else:  # 1000+ users
            return cls(
                cache_shards=64,
                cache_max_size_per_shard=3000,
                max_concurrent_optimizations=200,
                max_queued_requests=2000,
                max_optimization_workers=16,
                max_io_workers=100,
                gc_threshold_mb=2000,
            )


# Global config - can be updated at startup
_config = ScalabilityConfig()


def configure_for_scale(expected_users: int) -> None:
    """Configure the system for expected concurrent user load."""
    global _config
    _config = ScalabilityConfig.for_load(expected_users)
    logger.info(f"🔧 Configured for {expected_users} concurrent users: {_config}")


# ============================================================================
# METRICS COLLECTION - For monitoring at scale
# ============================================================================

@dataclass
class Metrics:
    """Thread-safe metrics collection for monitoring."""
    _lock: Lock = field(default_factory=Lock)
    
    # Request metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    queued_requests: int = 0
    rejected_requests: int = 0  # Rejected due to backpressure
    
    # Timing metrics (in ms)
    total_queue_wait_time: float = 0.0
    total_processing_time: float = 0.0
    max_queue_wait_time: float = 0.0
    max_processing_time: float = 0.0
    
    # Cache metrics
    cache_hits: int = 0
    cache_misses: int = 0
    cache_evictions: int = 0
    
    def record_request_start(self) -> float:
        """Record request start, return timestamp."""
        with self._lock:
            self.total_requests += 1
            self.queued_requests += 1
        return time.perf_counter()
    
    def record_queue_complete(self, start_time: float) -> float:
        """Record queue wait complete, return new timestamp."""
        now = time.perf_counter()
        wait_time = (now - start_time) * 1000
        with self._lock:
            self.queued_requests -= 1
            self.total_queue_wait_time += wait_time
            self.max_queue_wait_time = max(self.max_queue_wait_time, wait_time)
        return now
    
    def record_success(self, processing_start: float) -> None:
        """Record successful request completion."""
        processing_time = (time.perf_counter() - processing_start) * 1000
        with self._lock:
            self.successful_requests += 1
            self.total_processing_time += processing_time
            self.max_processing_time = max(self.max_processing_time, processing_time)
    
    def record_failure(self) -> None:
        """Record failed request."""
        with self._lock:
            self.failed_requests += 1
    
    def record_rejection(self) -> None:
        """Record rejected request (backpressure)."""
        with self._lock:
            self.rejected_requests += 1
            self.total_requests += 1
    
    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1
    
    def record_cache_miss(self) -> None:
        with self._lock:
            self.cache_misses += 1
    
    def record_cache_eviction(self, count: int = 1) -> None:
        with self._lock:
            self.cache_evictions += count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        with self._lock:
            completed = self.successful_requests + self.failed_requests
            return {
                'total_requests': self.total_requests,
                'successful_requests': self.successful_requests,
                'failed_requests': self.failed_requests,
                'queued_requests': self.queued_requests,
                'rejected_requests': self.rejected_requests,
                'success_rate': self.successful_requests / max(1, completed),
                'avg_queue_wait_ms': self.total_queue_wait_time / max(1, completed),
                'max_queue_wait_ms': self.max_queue_wait_time,
                'avg_processing_ms': self.total_processing_time / max(1, self.successful_requests),
                'max_processing_ms': self.max_processing_time,
                'cache_hit_rate': self.cache_hits / max(1, self.cache_hits + self.cache_misses),
                'cache_evictions': self.cache_evictions,
            }
    
    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self.total_requests = 0
            self.successful_requests = 0
            self.failed_requests = 0
            self.queued_requests = 0
            self.rejected_requests = 0
            self.total_queue_wait_time = 0.0
            self.total_processing_time = 0.0
            self.max_queue_wait_time = 0.0
            self.max_processing_time = 0.0
            self.cache_hits = 0
            self.cache_misses = 0
            self.cache_evictions = 0


# Global metrics instance
metrics = Metrics()


# ============================================================================
# SHARDED TTL CACHE - High-concurrency caching with LRU eviction
# ============================================================================

class CacheShard:
    """A single shard of the cache with its own lock and LRU eviction."""
    
    def __init__(self, ttl_seconds: int, max_size: int):
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = Lock()
    
    def get(self, key: str) -> Tuple[Optional[Any], bool]:
        """Get value if not expired. Returns (value, was_hit)."""
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if (time.time() - timestamp) < self._ttl:
                    # Move to end (most recently used)
                    self._cache.move_to_end(key)
                    return value, True
                # Expired - remove it
                del self._cache[key]
        return None, False
    
    def set(self, key: str, value: Any) -> int:
        """Set value. Returns number of evictions."""
        evictions = 0
        with self._lock:
            # Remove if exists (to update position)
            if key in self._cache:
                del self._cache[key]
            
            # Evict oldest entries if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)  # Remove oldest
                evictions += 1
            
            self._cache[key] = (value, time.time())
        
        return evictions
    
    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if existed."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
        return False
    
    def clear(self) -> int:
        """Clear all entries. Returns count cleared."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.time()
        removed = 0
        with self._lock:
            expired_keys = [
                key for key, (_, timestamp) in self._cache.items()
                if (now - timestamp) >= self._ttl
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1
        return removed
    
    def size(self) -> int:
        """Get current size."""
        with self._lock:
            return len(self._cache)


class ShardedTTLCache:
    """
    High-concurrency cache with TTL expiration and LRU eviction.
    
    Uses multiple shards (each with its own lock) to reduce contention.
    Keys are distributed across shards using consistent hashing.
    
    Usage:
        cache = ShardedTTLCache(ttl_seconds=300, num_shards=16, max_size_per_shard=10000)
        cache.set('key', value)
        value = cache.get('key')  # Returns None if expired or missing
    """
    
    def __init__(
        self, 
        ttl_seconds: int = 300, 
        num_shards: int = None,
        max_size_per_shard: int = None
    ):
        num_shards = num_shards or _config.cache_shards
        max_size_per_shard = max_size_per_shard or _config.cache_max_size_per_shard
        
        self._num_shards = num_shards
        self._shards = [
            CacheShard(ttl_seconds, max_size_per_shard)
            for _ in range(num_shards)
        ]
        self._ttl = ttl_seconds
    
    def _get_shard(self, key: str) -> CacheShard:
        """Get the shard for a key using consistent hashing."""
        hash_val = int(hashlib.md5(key.encode()).hexdigest(), 16)
        return self._shards[hash_val % self._num_shards]
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        shard = self._get_shard(key)
        value, was_hit = shard.get(key)
        if was_hit:
            metrics.record_cache_hit()
        else:
            metrics.record_cache_miss()
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp."""
        shard = self._get_shard(key)
        evictions = shard.set(key, value)
        if evictions > 0:
            metrics.record_cache_eviction(evictions)
    
    def delete(self, key: str) -> bool:
        """Delete a key from cache. Returns True if key existed."""
        shard = self._get_shard(key)
        return shard.delete(key)
    
    def clear(self) -> int:
        """Clear all cache entries. Returns count of cleared items."""
        total = sum(shard.clear() for shard in self._shards)
        return total
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed items."""
        total = sum(shard.cleanup_expired() for shard in self._shards)
        return total
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = sum(shard.size() for shard in self._shards)
        return {
            'total_entries': total_entries,
            'num_shards': self._num_shards,
            'ttl_seconds': self._ttl,
            'avg_entries_per_shard': total_entries / self._num_shards,
        }


# ============================================================================
# REQUEST QUEUE - Backpressure-aware request handling
# ============================================================================

class RequestQueue:
    """
    Manages concurrent request execution with backpressure.
    
    Limits the number of simultaneous heavy operations (like optimizations)
    and queues excess requests. Rejects requests when queue is full.
    
    Usage:
        queue = RequestQueue(max_concurrent=50, max_queued=500)
        
        with queue.acquire(timeout=30.0) as acquired:
            if acquired:
                # Do heavy work
                result = run_optimization(...)
            else:
                # Queue was full, return error to client
                return "Server busy, try again later"
    """
    
    def __init__(
        self, 
        max_concurrent: int = None, 
        max_queued: int = None,
        default_timeout: float = None
    ):
        self._max_concurrent = max_concurrent or _config.max_concurrent_optimizations
        self._max_queued = max_queued or _config.max_queued_requests
        self._default_timeout = default_timeout or _config.request_timeout
        
        self._semaphore = Semaphore(self._max_concurrent)
        self._queue_lock = Lock()
        self._queued_count = 0
        self._active_count = 0
        self._condition = Condition(self._queue_lock)
    
    def acquire(self, timeout: float = None) -> 'RequestQueueContext':
        """
        Acquire a slot in the request queue.
        Returns a context manager that should be used in a `with` statement.
        """
        return RequestQueueContext(self, timeout or self._default_timeout)
    
    def _try_acquire(self, timeout: float) -> bool:
        """Try to acquire a slot. Returns True if acquired."""
        # First, try to join the queue
        with self._queue_lock:
            if self._queued_count >= self._max_queued:
                # Queue is full - reject
                metrics.record_rejection()
                return False
            self._queued_count += 1
        
        # Record that we're waiting
        start_time = metrics.record_request_start()
        
        try:
            # Wait for a processing slot
            acquired = self._semaphore.acquire(timeout=timeout)
            
            if acquired:
                # Got a slot - move from queued to active
                with self._queue_lock:
                    self._queued_count -= 1
                    self._active_count += 1
                metrics.record_queue_complete(start_time)
                return True
            else:
                # Timeout - remove from queue
                with self._queue_lock:
                    self._queued_count -= 1
                metrics.record_failure()
                return False
                
        except Exception:
            with self._queue_lock:
                self._queued_count -= 1
            metrics.record_failure()
            raise
    
    def _release(self) -> None:
        """Release a slot back to the pool."""
        with self._queue_lock:
            self._active_count -= 1
        self._semaphore.release()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current queue status."""
        with self._queue_lock:
            return {
                'max_concurrent': self._max_concurrent,
                'max_queued': self._max_queued,
                'active': self._active_count,
                'queued': self._queued_count,
                'available_slots': self._max_concurrent - self._active_count,
                'queue_utilization': self._queued_count / self._max_queued,
            }


class RequestQueueContext:
    """Context manager for request queue slots."""
    
    def __init__(self, queue: RequestQueue, timeout: float):
        self._queue = queue
        self._timeout = timeout
        self._acquired = False
        self._processing_start: Optional[float] = None
    
    def __enter__(self) -> bool:
        """Try to acquire a slot. Returns True if acquired."""
        self._acquired = self._queue._try_acquire(self._timeout)
        if self._acquired:
            self._processing_start = time.perf_counter()
        return self._acquired
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Release the slot if acquired."""
        if self._acquired:
            if exc_type is None and self._processing_start:
                metrics.record_success(self._processing_start)
            else:
                metrics.record_failure()
            self._queue._release()


# Global request queue for optimizations
optimization_queue = RequestQueue()

# ============================================================================
# EXECUTORS - LAZY INITIALIZATION to avoid timeout on Flask reload
# ============================================================================
# The optimizer mutates large Polars-backed objects and performs a meaningful
# amount of Python-side pre/post processing around the CVXPY solve. A dedicated
# optimization thread pool gives us isolation from blocking I/O without forcing
# object pickling or cross-process serialization overhead.

# Determine optimal worker counts based on CPU cores
_cpu_count = multiprocessing.cpu_count()

def _get_optimization_workers() -> int:
    """Get number of optimization workers based on config."""
    return min(_cpu_count, _config.max_optimization_workers)

def _get_io_workers() -> int:
    """Get number of I/O workers based on config."""
    return min(_cpu_count * 2, _config.max_io_workers)

logger.info(f"🔧 CPU cores: {_cpu_count}, Max optimization workers: {_config.max_optimization_workers}, Max I/O workers: {_config.max_io_workers}")

# Lazy-initialized executors (created on first use)
_optimization_executor: Optional[ThreadPoolExecutor] = None
_blocking_io_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = Lock()


def get_optimization_executor() -> ThreadPoolExecutor:
    """
    Get the shared optimization executor.

    This pool is intentionally separate from blocking I/O so expensive solves
    cannot starve database/API work.
    """
    global _optimization_executor
    if _optimization_executor is None:
        with _executor_lock:
            if _optimization_executor is None:
                workers = _get_optimization_workers()
                logger.info(f"🚀 Initializing optimization ThreadPoolExecutor with {workers} workers")
                _optimization_executor = ThreadPoolExecutor(
                    max_workers=workers,
                    thread_name_prefix="optimization",
                )
    return _optimization_executor


def get_blocking_io_executor() -> ThreadPoolExecutor:
    """
    Get the shared blocking I/O thread pool executor.
    Lazily initialized on first call.
    """
    global _blocking_io_executor
    if _blocking_io_executor is None:
        with _executor_lock:
            if _blocking_io_executor is None:
                workers = _get_io_workers()
                logger.info(f"🚀 Initializing ThreadPoolExecutor with {workers} workers")
                _blocking_io_executor = ThreadPoolExecutor(
                    max_workers=workers, 
                    thread_name_prefix="blocking_io"
                )
    return _blocking_io_executor


def run_in_executor(executor: ThreadPoolExecutor, func: Callable, *args, **kwargs):
    """
    Submit a function to run in a thread pool executor.
    Returns a Future that can be awaited or have result() called.
    """
    if kwargs:
        return executor.submit(lambda: func(*args, **kwargs))
    return executor.submit(func, *args)


# ============================================================================
# TTL CACHE - Backward-compatible wrapper using ShardedTTLCache
# ============================================================================

class TTLCache(ShardedTTLCache):
    """
    Thread-safe cache with TTL (Time-To-Live) expiration.
    
    This is now a wrapper around ShardedTTLCache for backward compatibility.
    For new code, consider using ShardedTTLCache directly with explicit shard config.
    
    Usage:
        cache = TTLCache(ttl_seconds=300)
        cache.set('key', value)
        value = cache.get('key')  # Returns None if expired or missing
    """
    
    def __init__(self, ttl_seconds: int = 300):
        # Use 4 shards for simple TTLCache (good balance for moderate load)
        super().__init__(ttl_seconds=ttl_seconds, num_shards=4, max_size_per_shard=25000)
        # For backward compatibility, expose internal cache reference
        # Note: This is a simplified view - actual data is distributed across shards
        self._cache = {}
        self._ttl = ttl_seconds
        self._lock = Lock()
    
    @property 
    def _cache(self) -> Dict:
        """Backward compatibility: return merged view of all shard caches."""
        merged = {}
        for shard in self._shards:
            with shard._lock:
                for key, (value, timestamp) in shard._cache.items():
                    merged[key] = (value, datetime.fromtimestamp(timestamp))
        return merged
    
    @_cache.setter
    def _cache(self, value: Dict) -> None:
        """Backward compatibility: no-op setter."""
        pass


# ============================================================================
# SHARED CACHES - Module-level singletons (using ShardedTTLCache for scale)
# ============================================================================

# Allocation models (change rarely) - high shard count for read-heavy load
allocations_cache = ShardedTTLCache(ttl_seconds=300, num_shards=8, max_size_per_shard=5000)

# Allocation details per model - larger data, more shards
allocation_details_cache = ShardedTTLCache(ttl_seconds=600, num_shards=16, max_size_per_shard=2000)

# Account validation results (short TTL for security)
account_cache = ShardedTTLCache(ttl_seconds=60, num_shards=8, max_size_per_shard=10000)

# Portfolio data (moderate TTL) - most frequently accessed
portfolio_cache = ShardedTTLCache(ttl_seconds=120, num_shards=16, max_size_per_shard=5000)

# Optimization results cache (longer TTL since computationally expensive)
optimization_results_cache = ShardedTTLCache(ttl_seconds=1800, num_shards=8, max_size_per_shard=1000)


def clear_all_caches() -> Dict[str, int]:
    """Clear all caches and return count of cleared items"""
    return {
        'allocations': allocations_cache.clear(),
        'allocation_details': allocation_details_cache.clear(),
        'account': account_cache.clear(),
        'portfolio': portfolio_cache.clear(),
        'optimization_results': optimization_results_cache.clear(),
    }


def get_all_cache_stats() -> Dict[str, Any]:
    """Get statistics for all caches."""
    return {
        'allocations': allocations_cache.stats(),
        'allocation_details': allocation_details_cache.stats(),
        'account': account_cache.stats(),
        'portfolio': portfolio_cache.stats(),
        'optimization_results': optimization_results_cache.stats(),
        'global_metrics': metrics.get_stats(),
    }


# ============================================================================
# FILE STORAGE HELPERS - For multi-instance scaling on Azure
# ============================================================================

def get_results_dir() -> str:
    """
    Get results directory path.
    On Azure App Service, uses /home which is shared across instances.
    Locally, uses instance/ directory.
    """
    if os.environ.get('WEBSITE_SITE_NAME'):  # Running on Azure
        base_dir = '/home/site/optimization_results'
    else:
        # Local development
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            'instance', 'optimization_results'
        )
    
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def _sanitize_result_id(result_id: str) -> str:
    """Sanitize result_id to prevent path traversal."""
    import re
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '', str(result_id))
    if not clean:
        raise ValueError("Invalid result_id")
    return clean


def get_result_file_path(result_id: str) -> str:
    """Get full path to a result file by ID"""
    result_id = _sanitize_result_id(result_id)
    return os.path.join(get_results_dir(), f'optimization_{result_id}.pkl')


def result_exists(result_id: str) -> bool:
    """Check if a result file exists"""
    return os.path.exists(get_result_file_path(result_id))


def load_cached_result(result_id: str) -> Optional[Any]:
    """Load a result payload from in-memory cache or shared storage."""
    cache_key = f"result:{result_id}"
    cached = optimization_results_cache.get(cache_key)
    if cached is not None:
        return cached

    result_file = get_result_file_path(result_id)
    if not os.path.exists(result_file):
        return None

    import pickle

    with open(result_file, "rb") as f:
        payload = pickle.load(f)

    optimization_results_cache.set(cache_key, payload)
    return payload


def store_cached_result(result_id: str, payload: Any, result_file: Optional[str] = None) -> str:
    """Persist a result payload and prime the in-memory cache."""
    import pickle

    result_file = result_file or get_result_file_path(result_id)
    with open(result_file, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    optimization_results_cache.set(f"result:{result_id}", payload)
    return result_file


# ============================================================================
# ASYNC HELPERS
# ============================================================================

T = TypeVar('T')


def run_async(coro) -> Any:
    """
    Run an async coroutine from synchronous Flask code.
    Creates a new event loop per call (safe with Flask + Gunicorn).
    
    Usage:
        result = run_async(some_async_function())
    """
    return asyncio.run(coro)


async def gather_with_timeout(*coros, timeout: float = 30.0) -> tuple:
    """
    Run multiple coroutines concurrently with a timeout.
    
    Usage:
        results = await gather_with_timeout(
            fetch_portfolio(),
            fetch_allocation(),
            fetch_security_info(),
            timeout=15.0
        )
    """
    try:
        return await asyncio.wait_for(
            asyncio.gather(*coros, return_exceptions=True),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"Async gather timed out after {timeout}s")
        raise


def cached(cache: TTLCache, key_func: Callable[..., str] = None):
    """
    Decorator for caching function results.
    
    Usage:
        @cached(allocations_cache, key_func=lambda model: f"alloc_{model}")
        def get_allocation(model: str):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # Check cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_value
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result)
            logger.debug(f"Cached result for {cache_key}")
            
            return result
        
        return wrapper
    return decorator


def async_cached(cache: TTLCache, key_func: Callable[..., str] = None):
    """
    Decorator for caching async function results.
    
    Usage:
        @async_cached(allocations_cache, key_func=lambda model: f"alloc_{model}")
        async def get_allocation(model: str):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # Check cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_value
            
            # Execute async function
            result = await func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result)
            logger.debug(f"Cached result for {cache_key}")
            
            return result
        
        return wrapper
    return decorator


# ============================================================================
# BACKGROUND CLEANUP TASK
# ============================================================================

_cleanup_thread: Optional[Thread] = None
_cleanup_stop_event: Optional[Event] = None


def _background_cleanup_loop():
    """Background thread that periodically cleans up expired cache entries."""
    while not _cleanup_stop_event.is_set():
        try:
            # Wait for interval or stop signal
            if _cleanup_stop_event.wait(timeout=_config.cache_cleanup_interval):
                break  # Stop event was set
            
            # Cleanup expired entries from all caches
            total_cleaned = 0
            for cache in [allocations_cache, allocation_details_cache, 
                         account_cache, portfolio_cache, optimization_results_cache]:
                total_cleaned += cache.cleanup_expired()
            
            if total_cleaned > 0:
                logger.debug(f"🧹 Background cleanup removed {total_cleaned} expired cache entries")
                
        except Exception as e:
            logger.warning(f"Error in background cleanup: {e}")


def start_background_cleanup():
    """Start the background cleanup thread."""
    global _cleanup_thread, _cleanup_stop_event
    
    if _cleanup_thread is not None and _cleanup_thread.is_alive():
        return  # Already running
    
    _cleanup_stop_event = Event()
    _cleanup_thread = Thread(
        target=_background_cleanup_loop,
        daemon=True,
        name="cache_cleanup"
    )
    _cleanup_thread.start()
    logger.info("🧹 Started background cache cleanup thread")


def stop_background_cleanup():
    """Stop the background cleanup thread."""
    global _cleanup_thread, _cleanup_stop_event
    
    if _cleanup_stop_event is not None:
        _cleanup_stop_event.set()
    
    if _cleanup_thread is not None:
        _cleanup_thread.join(timeout=5.0)
        _cleanup_thread = None
    
    if logger.handlers:
        logger.info("🧹 Stopped background cache cleanup thread")


# ============================================================================
# CLEANUP
# ============================================================================

def shutdown_executors():
    """Shutdown all executors gracefully (non-blocking to avoid reload timeout)"""
    global _optimization_executor, _blocking_io_executor
    
    if logger.handlers:
        logger.info("Shutting down executors...")
    
    # Stop background cleanup
    stop_background_cleanup()
    
    # Use wait=False to avoid blocking during Flask reload
    # Running tasks will complete, but we won't wait for them
    if _optimization_executor is not None:
        try:
            _optimization_executor.shutdown(wait=False, cancel_futures=True)
            _optimization_executor = None
        except Exception as e:
            logger.warning(f"Error shutting down optimization executor: {e}")
    
    if _blocking_io_executor is not None:
        try:
            _blocking_io_executor.shutdown(wait=False, cancel_futures=True)
            _blocking_io_executor = None
        except Exception as e:
            logger.warning(f"Error shutting down ThreadPoolExecutor: {e}")
    
    if logger.handlers:
        logger.info("Executors shut down")


# Register shutdown on module unload (optional, for clean exits)
import atexit
atexit.register(shutdown_executors)

# Start background cleanup on module load
start_background_cleanup()
