"""Small in-process sliding-window limiter for sensitive API endpoints.

The limiter intentionally provides a safe baseline for a single API process.
Production deployments with multiple replicas should also enforce equivalent
limits at the gateway or through a shared Redis-backed implementation.
"""

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

# 键数量上限：超过后主动清理过期键；清理后仍超限则拒绝新键（防键轮换攻击）
_MAX_KEYS = 10_000


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        # 每键独立锁：避免全局单锁成为高并发热点
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_sweep = time.monotonic()

    def _sweep_if_needed(self, now: float, threshold: float) -> None:
        """键数超限时清理完全过期的键；仍超限则清空最旧键直到回到上限。"""
        if len(self._requests) <= _MAX_KEYS:
            return
        if now - self._last_sweep < 10:
            # 清理频率限制：避免每请求都做全量扫描
            stale = [k for k, items in self._requests.items() if not items or items[-1] <= threshold]
            for k in stale:
                self._requests.pop(k, None)
                self._locks.pop(k, None)
            self._last_sweep = now
        if len(self._requests) <= _MAX_KEYS:
            return
        # 键轮换攻击兜底：按最旧活动时间淘汰超限部分
        ordered = sorted(
            ((k, items[-1]) for k, items in self._requests.items() if items),
            key=lambda kv: kv[1],
        )
        overflow = len(self._requests) - _MAX_KEYS
        for k, _ in ordered[:overflow]:
            self._requests.pop(k, None)
            self._locks.pop(k, None)

    async def check(self, key: str, *, limit: int, window_seconds: int) -> int | None:
        """Return retry-after seconds when over limit; otherwise record the request."""
        now = time.monotonic()
        lock = self._locks[key]
        async with lock:
            timestamps = self._requests[key]
            threshold = now - window_seconds
            while timestamps and timestamps[0] <= threshold:
                timestamps.popleft()
            if len(timestamps) >= limit:
                return max(1, int(window_seconds - (now - timestamps[0])) + 1)
            timestamps.append(now)

            # Keep the process cache bounded even if an attacker rotates keys.
            self._sweep_if_needed(now, threshold)
            return None

    async def reset(self) -> None:
        """Test helper; also useful for controlled local maintenance."""
        self._requests.clear()
        self._locks.clear()


limiter = SlidingWindowRateLimiter()


async def enforce_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    retry_after = await limiter.check(key, limit=limit, window_seconds=window_seconds)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )
