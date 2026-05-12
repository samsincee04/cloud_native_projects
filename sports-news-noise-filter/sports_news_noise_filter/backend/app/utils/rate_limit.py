"""Lightweight in-memory token-bucket rate limiting per client IP."""

from __future__ import annotations

import math
import os
import threading
import time

from starlette.requests import Request


class RateLimitExceeded(Exception):
    """Raised when a client exceeds its bucket; handled globally into HTTP 429."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds


class TokenBucket:
    def __init__(self, capacity: float, refill_per_second: float) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.tokens = float(capacity)
        self.last = time.monotonic()

    def consume(self, n: float = 1.0) -> tuple[bool, float]:
        now = time.monotonic()
        elapsed = now - self.last
        self.tokens = min(
            self.capacity, self.tokens + elapsed * self.refill_per_second
        )
        self.last = now
        if self.tokens >= n:
            self.tokens -= n
            return True, 0.0
        shortfall = n - self.tokens
        wait = (
            shortfall / self.refill_per_second
            if self.refill_per_second > 0
            else 60.0
        )
        return False, wait


_buckets: dict[tuple[str, str], TokenBucket] = {}
_bucket_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    host = getattr(getattr(request, "client", None), "host", None)
    if isinstance(host, str) and host.strip():
        return host.strip()
    return "unknown"


def _limit_per_minute(kind: str) -> float:
    env_map = {
        "feed": "RATE_LIMIT_PER_MINUTE_FEED",
        "cluster": "RATE_LIMIT_PER_MINUTE_CLUSTER",
        "write": "RATE_LIMIT_PER_MINUTE_WRITE",
    }
    defaults = {"feed": 60.0, "cluster": 120.0, "write": 30.0}
    key = env_map[kind]
    try:
        raw = float(os.getenv(key, str(defaults[kind])))
    except ValueError:
        raw = defaults[kind]
    return max(1.0, min(10_000.0, raw))


def check_rate_limit(request: Request, kind: str, route_label: str) -> None:
    """
    ``kind`` is one of: feed, cluster, write.
    Raises RateLimitExceeded when over limit.
    """
    ip = _client_ip(request)
    limit = _limit_per_minute(kind)
    refill_per_sec = limit / 60.0
    key = (kind, ip)
    with _bucket_lock:
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(capacity=limit, refill_per_second=refill_per_sec)
            _buckets[key] = bucket
        ok, wait_s = bucket.consume(1.0)
    if ok:
        return
    retry_after = int(min(30, max(5, math.ceil(wait_s))))
    print(
        f"rate_limited ip={ip} route={route_label} retry_after_s={retry_after}",
        flush=True,
    )
    raise RateLimitExceeded(retry_after)


def rate_limit_feed_clusters(request: Request) -> None:
    check_rate_limit(request, "feed", "GET /feed_clusters")


def rate_limit_cluster_detail(request: Request) -> None:
    check_rate_limit(request, "cluster", "GET /clusters/{cluster_id}")


def rate_limit_users_post(request: Request) -> None:
    check_rate_limit(request, "write", "POST /users")


def rate_limit_preferences_put(request: Request) -> None:
    check_rate_limit(request, "write", "PUT /users/{user_id}/preferences")
