"""
自定义异常类 - 统一错误处理
"""

from typing import Any, Dict, Optional


class SalesAIException(Exception):
    """基础异常类"""
    
    def __init__(
        self, 
        message: str, 
        code: str = "UNKNOWN_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class IntentRecognitionError(SalesAIException):
    """意图识别失败异常"""
    
    def __init__(self, message: str = "无法识别用户意图", details: Optional[Dict] = None):
        super().__init__(message, code="INTENT_RECOGNITION_ERROR", details=details)


class DocumentGenerationError(SalesAIException):
    """文档生成失败异常"""
    
    def __init__(self, message: str = "文档生成失败", details: Optional[Dict] = None):
        super().__init__(message, code="DOCUMENT_GENERATION_ERROR", details=details)


class KnowledgeBaseError(SalesAIException):
    """知识库查询失败异常"""
    
    def __init__(self, message: str = "知识库查询失败", details: Optional[Dict] = None):
        super().__init__(message, code="KNOWLEDGE_BASE_ERROR", details=details)


class ValidationError(SalesAIException):
    """参数校验失败异常"""
    
    def __init__(self, message: str = "参数校验失败", details: Optional[Dict] = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class GraphExecutionError(SalesAIException):
    """LangGraph 执行异常"""
    
    def __init__(self, message: str = "工作流执行失败", details: Optional[Dict] = None):
        super().__init__(message, code="GRAPH_EXECUTION_ERROR", details=details)
