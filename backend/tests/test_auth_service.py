"""认证服务安全回归测试（SECRET_KEY 校验 / 密码长度 / Cookie / 令牌吊销）。"""

import pytest
from pydantic import ValidationError

from app.services.auth import (
    _validate_secret,
    build_auth_cookie,
    create_access_token,
    AUTH_COOKIE_NAME,
    ALGORITHM,
    SECRET_KEY,
)
from app.models.auth import UserCreate


def test_rejects_placeholder_secrets():
    for bad in ("", "replace-with-a-random-secret", "changeme", "secret", "short"):
        with pytest.raises(RuntimeError):
            _validate_secret(bad)


def test_accepts_strong_secret():
    _validate_secret("x" * 32)


def test_password_over_72_bytes_rejected():
    with pytest.raises(ValidationError):
        UserCreate(username="alice", password="密" * 30)  # 90 UTF-8 字节 > 72


def test_password_within_72_bytes_ok():
    user = UserCreate(username="alice", password="a" * 8)
    assert user.username == "alice"


def test_auth_cookie_is_httponly_and_scoped():
    cookie = build_auth_cookie("token-value")
    assert cookie["key"] == AUTH_COOKIE_NAME
    assert cookie["httponly"] is True
    assert cookie["path"] == "/"
    assert cookie["samesite"] == "lax"


def test_jwt_roundtrip_contains_version():
    from jose import jwt

    token = create_access_token({"sub": "1", "username": "admin", "role": "admin", "ver": 3})
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "1"
    assert payload["ver"] == 3
    assert "exp" in payload
