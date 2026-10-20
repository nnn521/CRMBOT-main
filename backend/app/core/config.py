"""
核心配置模块 - 管理所有环境变量和配置项

重构更新：
- embedding_model 改为 bge-m3 (BAAI 中英双语嵌入模型)
- 路径默认值锚定 backend/ 目录（绝对路径），不再依赖进程 CWD
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录绝对路径（config.py 位于 backend/app/core/ 下）
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """应用配置类，自动从环境变量加载"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # 应用基础配置
    app_name: str = Field(default="智能销售 AI Agent", description="应用名称")
    app_version: str = Field(default="1.0.0", description="应用版本")
    debug: bool = Field(default=False, description="调试模式")
    
    # API 配置
    api_v1_prefix: str = Field(default="/api/v1", description="API 版本前缀")
    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=8000, description="服务端口")
    
    # CORS 配置
    cors_origins: List[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="允许的跨域来源；生产环境必须显式配置为受控 HTTPS 域名"
    )
    
    # LLM 配置（OpenAI 兼容接口，默认 DeepSeek）
    openai_api_key: Optional[str] = Field(default=None, description="DeepSeek API Key")
    openai_base_url: Optional[str] = Field(
        default="https://api.deepseek.com/v1",
        description="DeepSeek API Base URL"
    )
    default_model: str = Field(default="deepseek-chat", description="默认使用的模型")
    
    # Embedding 配置（Ollama）
    embedding_model: str = Field(
        default="bge-m3",
        description="Ollama 向量化模型 (BAAI BGE-M3 中英双语)"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama 服务地址"
    )
    
    # LangGraph 配置
    max_iterations: int = Field(default=10, description="最大迭代次数，防止死循环")
    auth_rate_limit: int = Field(default=10, ge=1, le=1000, description="认证接口限流次数")
    chat_rate_limit: int = Field(default=30, ge=1, le=1000, description="单用户聊天接口限流次数")
    report_rate_limit: int = Field(default=10, ge=1, le=1000, description="报表 AI 分析接口限流次数")
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600, description="限流滑动窗口秒数")
    
    # PostgreSQL 数据库配置（持久化）
    database_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL 连接字符串（用于 LangGraph 状态持久化）"
    )
    
    # 知识库配置
    knowledge_base_path: str = Field(
        default=str(_BACKEND_DIR / "data" / "knowledge_base"),
        description="知识库文件存储路径"
    )
    vector_store_path: str = Field(
        default=str(_BACKEND_DIR / "data" / "vector_store"),
        description="向量数据库存储路径"
    )
    
    # RAG v2：独立开关/连接，不回退到业务数据库或现有模型配置
    rag_v2_enabled: bool = False
    knowledge_database_url: Optional[str] = None
    knowledge_embedding_model: str = "bge-m3"
    knowledge_embedding_revision: str = ""  # 必须配置 Ollama /api/tags 的完整 digest
    knowledge_embedding_dimension: int = Field(default=1024, ge=1, le=16000)
    knowledge_ollama_base_url: str = "http://localhost:11434"
    knowledge_http_timeout_seconds: float = Field(default=10, gt=0, le=120)
    knowledge_database_timeout_seconds: int = Field(default=5, ge=1, le=60)
    knowledge_upload_max_bytes: int = Field(default=262144, ge=1, le=2097152)
    knowledge_max_build_chunks: int = Field(default=2000, ge=1, le=10000)
    # 可选本地 TEI cross-encoder；不安装/启动模型，默认完全不调用
    knowledge_rerank_enabled: bool = False
    knowledge_rerank_base_url: str = "http://127.0.0.1:8081"
    knowledge_rerank_model: str = ""  # 必须匹配 TEI /info.model_id
    knowledge_rerank_timeout_seconds: float = Field(default=0.3, gt=0, le=0.3)
    knowledge_rerank_min_candidates: int = Field(default=4, ge=2, le=20)
    knowledge_rerank_max_relative_gap: float = Field(default=0.15, ge=0, le=1)
    knowledge_api_key: Optional[str] = None
    knowledge_api_base_url: str = "https://api.deepseek.com"
    knowledge_answer_model: str = "deepseek-chat"
    knowledge_budget_cny: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    knowledge_input_per_million_cny: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    knowledge_output_per_million_cny: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    knowledge_budget_path: str = str(_BACKEND_DIR / "data" / "knowledge_model_budget.sqlite3")
    # answered: 单次结构化综合回答（仍需人工评测）；source_quotes_only: 完整原文摘录
    knowledge_answer_mode: Literal["source_quotes_only", "synthesized"] = "source_quotes_only"

    # 文档生成配置
    output_dir: str = Field(
        default=str(_BACKEND_DIR / "output"),
        description="生成文档的输出目录"
    )
    
    # 项目根目录（模板/图片等资源的定位基准，不再依赖 CWD）
    base_dir: str = Field(
        default=str(_BACKEND_DIR),
        description="项目根目录"
    )
    
    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="日志格式"
    )
    
    # 智谱AI 配置（GLM-4V 视觉识别 / CogView 图片生成）
    zhipu_api_key: str = Field(default="", description="智谱AI API Key (GLM-4V vision, CogView image generation)")
    
    # 运行环境配置
    environment: str = Field(default="development", description="运行环境: development / production")
    
    # JWT 认证配置
    secret_key: str = Field(default="", description="JWT secret key（至少 32 字符，禁止占位值）")
    bootstrap_admin_username: str = Field(default="", description="首次启动时创建的管理员用户名")
    bootstrap_admin_password: str = Field(default="", description="首次启动时创建的管理员密码")
    
    # Hermes 内部助手配置
    HERMES_API_URL: str = Field(
        default="http://localhost:8642/v1",
        description="Hermes Agent API 地址"
    )
    HERMES_API_KEY: str = Field(default="", description="Hermes API Server 密钥")

    @property
    def postgres_dsn(self) -> Optional[str]:
        """Return a psycopg-compatible DSN for LangGraph."""
        if not self.database_url:
            return None
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例（缓存以提高性能）"""
    return Settings()


# 全局配置实例
settings = get_settings()
