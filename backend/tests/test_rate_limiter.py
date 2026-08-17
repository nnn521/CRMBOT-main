"""Tests for local API abuse protection."""

import pytest
from fastapi import HTTPException

from app.services.rate_limiter import SlidingWindowRateLimiter, enforce_rate_limit, limiter


@pytest.mark.asyncio
async def test_sliding_window_rejects_the_request_after_limit():
    local_limiter = SlidingWindowRateLimiter()
    assert await local_limiter.check("customer:1", limit=2, window_seconds=60) is None
    assert await local_limiter.check("customer:1", limit=2, window_seconds=60) is None
    assert await local_limiter.check("customer:1", limit=2, window_seconds=60) >= 1


@pytest.mark.asyncio
async def test_enforce_rate_limit_returns_standard_429_and_retry_header():
    await limiter.reset()
    await enforce_rate_limit("test:429", limit=1, window_seconds=60)
    with pytest.raises(HTTPException) as error:
        await enforce_rate_limit("test:429", limit=1, window_seconds=60)
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"]
    await limiter.reset()
