"""
多租户 Mixin - 为所有业务表添加 tenant_id 字段

所有需要隔离租户数据的表都继承 TenantMixin。
当前阶段仅做字段预留，后续实现租户过滤中间件。
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class TenantMixin:
    """
    租户混入类

    为模型添加 tenant_id 字段，用于多租户数据隔离。
    当前阶段：字段存在但不做强制过滤。
    后续阶段：添加租户过滤中间件 + Row Level Security。
    """
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        default="default",
        nullable=False,
        index=True,
        comment="租户ID（多租户预留，默认 'default'）"
    )
