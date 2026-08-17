"""
数据库连接管理 - SQLAlchemy 异步引擎 + 会话工厂

提供：
- Base: SQLAlchemy 声明式基类
- get_db: 异步数据库会话依赖注入
- init_db: 建表（开发用，生产用 Alembic）
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


# 异步引擎（仅当 DATABASE_URL 配置了才创建）
engine = None
async_session_factory = None

if settings.database_url:
    # LangGraph 使用标准 PostgreSQL DSN；SQLAlchemy 使用 asyncpg 驱动。
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif not db_url.startswith("postgresql+asyncpg://"):
        raise ValueError("DATABASE_URL 必须是 PostgreSQL 连接字符串")

    engine = create_async_engine(
        db_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    async_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


async def get_db() -> AsyncSession:
    """
    FastAPI 依赖注入：获取数据库会话

    用法:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    if not async_session_factory:
        raise RuntimeError("数据库未配置，请设置 DATABASE_URL 环境变量")
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_optional():
    """
    可选的数据库会话 — 未配置数据库时回传 None 而不是失败。
    适用于数据库为可选功能的端点（如 chat 主流程）。
    """
    if not async_session_factory:
        yield None
        return
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """
    初始化数据库表结构（开发用）

    生产环境请使用 Alembic 迁移：
        alembic revision --autogenerate -m "init"
        alembic upgrade head
    """
    if not engine:
        return False
    # Import models here so every table is registered on Base.metadata.
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return True
