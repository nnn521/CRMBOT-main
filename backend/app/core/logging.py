"""
日志配置模块 - 统一应用日志格式和级别
"""

import logging
import json
import sys
from datetime import datetime, timezone

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter selected with LOG_FORMAT=json."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> logging.Logger:
    """配置并返回应用日志记录器"""
    
    # 创建日志记录器
    logger = logging.getLogger("sales_ai_agent")
    logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # 避免重复配置
    if logger.handlers:
        return logger
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    
    # 格式化器
    formatter = JsonFormatter() if settings.log_format.lower() == "json" else logging.Formatter(settings.log_format)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    # 文件处理器（生产环境建议开启）
    if not settings.debug:
        file_handler = logging.FileHandler("app.log", encoding="utf-8")
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """获取命名日志记录器"""
    if name:
        return logging.getLogger(f"sales_ai_agent.{name}")
    return logging.getLogger("sales_ai_agent")


# 应用启动时初始化
logger = setup_logging()
