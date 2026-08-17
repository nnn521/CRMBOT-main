"""
系统配置模型 - 运行时可调配置项

存储需要动态调整的配置（如欢迎语、默认折扣等），
与 .env 静态配置互补。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.tenant import TenantMixin


class SystemConfig(TenantMixin, Base):
    """系统配置表"""
    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="配置键"
    )
    config_value: Mapped[str] = mapped_column(
        Text, nullable=False, comment="配置值"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="配置说明"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否启用"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self):
        return f"<SystemConfig(key={self.config_key}, active={self.is_active})>"
