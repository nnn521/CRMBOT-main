"""SQLAlchemy model for username/password authentication accounts."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class AuthAccount(Base):
    """Login account used by both administrators and customers."""

    __tablename__ = "users_auth"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    # 令牌版本：登出/改密时 +1，使旧 JWT 全部失效（令牌吊销）
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
