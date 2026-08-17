"""
核心配置模块 - 管理所有环境变量和配置项

重构更新：
- embedding_model 改为 bge-m3 (BAAI 中英双语嵌入模型)
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        default="./data/knowledge_base",
        description="知识库文件存储路径"
    )
    vector_store_path: str = Field(
        default="./data/vector_store",
        description="向量数据库存储路径"
    )
    
    # 文档生成配置
    output_dir: str = Field(
        default="./output",
        description="生成文档的输出目录"
    )
    
    # 项目根目录
    base_dir: str = Field(
        default=".",
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
    secret_key: str = Field(default="", description="JWT secret key")
    internal_api_key: str = Field(
        default="", description="服务间 API Key；使用 get_api_key 的接口必须配置"
    )
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
