"""
CRMBOT - 智能销售 AI Agent 核心服务
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import chat_router, documents_router, images_router, ws_router, auth_router, sessions_router, reports_router, hermes_router, engagement_router
from app.api.v1.auth import ensure_users_table
from app.core.config import settings
from app.core.logging import get_logger
from app.agents.graphs.sales_graph import initialize_database
from app.models.db import engine, init_db

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭生命周期"""
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} 启动中...")
    
    # 初始化数据库
    if settings.database_url:
        business_db_ok = await init_db()
        await ensure_users_table()
        graph_db_ok = await initialize_database()
        if business_db_ok and graph_db_ok:
            logger.info("✅ 数据库初始化成功")
        else:
            logger.warning("⚠️ 数据库未完全初始化，Agent 将使用内存存储")
    else:
        logger.info("ℹ️ 未配置数据库，使用内存存储")
    
    yield
    
    logger.info("👋 服务关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="智能销售 AI Agent - CRMBOT",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat_router, prefix=settings.api_v1_prefix)
app.include_router(documents_router, prefix=settings.api_v1_prefix)
app.include_router(images_router, prefix=settings.api_v1_prefix)
app.include_router(ws_router, prefix=settings.api_v1_prefix, tags=["websocket"])
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(sessions_router, prefix=settings.api_v1_prefix)
app.include_router(reports_router, prefix=settings.api_v1_prefix)
app.include_router(hermes_router, prefix=settings.api_v1_prefix)
app.include_router(engagement_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
async def health():
    if engine is None:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "not_configured"},
        )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "unavailable"},
        )
    return {"status": "ok", "database": "connected"}
