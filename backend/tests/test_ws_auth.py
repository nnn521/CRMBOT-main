"""WebSocket 认证：Cookie 鉴权（不再接受 URL query token）。"""

import pytest

from app.api.v1.ws import _decode_ws_user
from app.services.auth import create_access_token, SECRET_KEY, ALGORITHM


class _FakeWebSocket:
    def __init__(self, cookies: dict | None = None, query_params: dict | None = None):
        self.cookies = cookies or {}
        self.query_params = query_params or {}


@pytest.mark.asyncio
async def test_ws_accepts_valid_cookie_token():
    token = create_access_token({"sub": "7", "username": "alice", "role": "customer", "ver": 0})
    ws = _FakeWebSocket(cookies={"crmbot_token": token})
    user = await _decode_ws_user(ws)
    assert user is not None
    assert user["sub"] == "7"


@pytest.mark.asyncio
async def test_ws_rejects_query_token_only():
    token = create_access_token({"sub": "7", "username": "alice", "role": "customer", "ver": 0})
    ws = _FakeWebSocket(query_params={"token": token})
    assert await _decode_ws_user(ws) is None


@pytest.mark.asyncio
async def test_ws_rejects_missing_and_invalid_token():
    assert await _decode_ws_user(_FakeWebSocket()) is None
    ws = _FakeWebSocket(cookies={"crmbot_token": "not-a-jwt"})
    assert await _decode_ws_user(ws) is None
