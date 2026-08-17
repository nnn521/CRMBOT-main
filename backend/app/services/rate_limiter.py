"""Small in-process sliding-window limiter for sensitive API endpoints.

The limiter intentionally provides a safe baseline for a single API process.
Production deployments with multiple replicas should also enforce equivalent
limits at the gateway or through a shared Redis-backed implementation.
"""

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, *, limit: int, window_seconds: int) -> int | None:
        """Return retry-after seconds when over limit; otherwise record the request."""
        now = time.monotonic()
        async with self._lock:
            timestamps = self._requests[key]
            threshold = now - window_seconds
            while timestamps and timestamps[0] <= threshold:
                timestamps.popleft()
            if len(timestamps) >= limit:
                return max(1, int(window_seconds - (now - timestamps[0])) + 1)
            timestamps.append(now)

            # Keep the process cache bounded even if an attacker rotates keys.
            if len(self._requests) > 10_000:
                stale_keys = [name for name, items in self._requests.items() if not items or items[-1] <= threshold]
                for stale_key in stale_keys:
                    self._requests.pop(stale_key, None)
            return None

    async def reset(self) -> None:
        """Test helper; also useful for controlled local maintenance."""
        async with self._lock:
            self._requests.clear()


limiter = SlidingWindowRateLimiter()


async def enforce_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    retry_after = await limiter.check(key, limit=limit, window_seconds=window_seconds)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )
