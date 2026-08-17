"""Regression tests for customer chat-session ownership checks."""

import pytest
from fastapi import HTTPException

from app.api.v1.chat import _assert_session_owner


class _OwnerResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, owner):
        self.owner = owner
        self.calls = 0

    async def execute(self, _statement):
        self.calls += 1
        return _OwnerResult(self.owner)


@pytest.mark.asyncio
async def test_customer_can_use_own_deterministic_initial_session():
    db = _FakeDb(None)
    await _assert_session_owner(db, "session_alice", {"user_id": 1, "username": "alice", "role": "customer"})
    assert db.calls == 0


@pytest.mark.asyncio
async def test_customer_is_denied_unknown_or_foreign_session():
    with pytest.raises(HTTPException) as error:
        await _assert_session_owner(
            _FakeDb(None), "session_bob", {"user_id": 1, "username": "alice", "role": "customer"}
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_customer_can_resume_a_session_with_own_persisted_messages():
    db = _FakeDb(object())
    await _assert_session_owner(
        db, "custom-session", {"user_id": 1, "username": "alice", "role": "customer"}
    )
    assert db.calls == 1
