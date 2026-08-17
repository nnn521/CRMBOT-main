"""
用户模型 - 存储终端用户信息（C端客户）

字段设计：
- open_id: 微信小程序 openid（唯一标识）
- nickname / phone / avatar: 基本信息
- tenant_id: 租户隔离（继承自 TenantMixin）
"""

from datetime import datetime

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.tenant import TenantMixin


class User(TenantMixin, Base):
    """终端用户表"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    open_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        comment="微信小程序 openid"
    )
    nickname: Mapped[str] = mapped_column(
        String(64), default="", comment="用户昵称"
    )
    phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="手机号"
    )
    avatar_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="头像 URL"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="注册时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self):
        return f"<User(id={self.id}, open_id={self.open_id}, nickname={self.nickname})>"
