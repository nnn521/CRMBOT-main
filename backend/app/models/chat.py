"""
聊天相关数据模型 - 定义 API 请求和响应结构
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class MessageRole(str, Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class UserIntent(str, Enum):
    """用户意图枚举 - 对应不同的销售场景（多模态汽车金牌销售顾问版）"""
    GENERAL_CHAT = "general_chat"           # 普通闲聊
    PRODUCT_INQUIRY = "product_inquiry"     # 产品咨询
    PRICE_NEGOTIATION = "price_negotiation" # 价格谈判
    DOCUMENT_REQUEST = "document_request"   # 请求生成文档
    QUOTE_GENERATION = "quote_generation"   # 生成报价单
    PROPOSAL_CREATION = "proposal_creation" # 创建提案书
    CONTRACT_DRAFTING = "contract_drafting" # 起草合同
    DATA_ANALYSIS = "data_analysis"         # 数据分析/报表
    PRESENTATION_REQUEST = "presentation_request"  # 请求演示文稿
    COMPLAINT_HANDLING = "complaint_handling"     # 投诉处理
    FOLLOW_UP = "follow_up"                 # 跟进提醒
    UNKNOWN = "unknown"                     # 未知意图
    
    # ═══════════════════════════════════════════════════════════════
    # 【多模态汽车金牌销售顾问 - 新增意图】
    # ═══════════════════════════════════════════════════════════════
    ANALYZE_CAR_IMAGE = "analyze_car_image"         # 分析汽车图片（车型识别、外观咨询）
    GENERATE_CUSTOM_CAR = "generate_custom_car"     # 生成定制汽车效果图/试驾视频
    SERVICE_APPOINTMENT = "service_appointment"     # 预约线下服务（购车/售后）


class DocumentType(str, Enum):
    """文档类型枚举"""
    DOCX = "docx"
    PDF = "pdf"
    XLSX = "xlsx"
    PPTX = "pptx"


class ChatMessage(BaseModel):
    """单条聊天消息模型"""
    role: MessageRole = Field(..., description="消息发送者角色")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[datetime] = Field(
        default_factory=datetime.now,
        description="消息时间戳"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="附加元数据（如引用的文档ID等）"
    )


class DocumentInfo(BaseModel):
    """生成的文档信息"""
    doc_type: DocumentType = Field(..., description="文档类型", serialization_alias="type")
    file_name: str = Field(..., description="文件名", serialization_alias="filename")
    file_path: str = Field(..., description="文件存储路径", serialization_alias="path")
    download_url: Optional[str] = Field(None, description="下载链接")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    generated_at: datetime = Field(default_factory=datetime.now)

    model_config = {"populate_by_name": True}


class ChatRequest(BaseModel):
    """
    聊天请求模型 - 前端传入的消息格式
    
    示例:
        {
            "session_id": "wx_user_123",
            "message": "帮我生成一份报价单",
            "history": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "您好！我是您的专属汽车顾问🏎️ 专注于保时捷/比亚迪全系车型！"}
            ],
            "context": {
                "customer_name": "张先生",
                "product_line": "保时捷911"
            }
        }
    """
    session_id: str = Field(..., description="会话唯一标识（建议使用微信 openid）")
    message: str = Field(..., min_length=1, max_length=10000, description="用户消息")
    history: List[ChatMessage] = Field(
        default_factory=list,
        description="历史消息上下文"
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="业务上下文（客户信息、产品信息等）"
    )
    
    @field_validator('message')
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('消息内容不能为空')
        return v.strip()


class ChatResponse(BaseModel):
    """
    聊天响应模型 - 返回给前端的数据
    
    示例:
        {
            "session_id": "wx_user_123",
            "reply": "好的，请提供以下信息...",
            "intent": "quote_generation",
            "documents": [],
            "suggested_actions": ["提供产品清单", "查看历史报价"],
            "metadata": {...}
        }
    """
    session_id: str = Field(..., description="会话ID")
    message_id: Optional[str] = Field(None, description="服务端生成的助手消息ID")
    user_message_id: Optional[str] = Field(None, description="服务端生成的用户消息ID")
    status: str = Field(default="completed", description="处理状态: completed/waiting_human")
    reply: str = Field(..., description="AI 回复内容")
    intent: UserIntent = Field(..., description="识别的用户意图")
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="本次对话生成的文档列表"
    )
    images: List[str] = Field(
        default_factory=list,
        description="相关车型图片URL列表"
    )
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="建议的下一步操作"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="附加元数据"
    )
    response_time_ms: Optional[int] = Field(
        None,
        description="响应耗时（毫秒）"
    )


class IntentAnalysisResult(BaseModel):
    """意图分析结果"""
    intent: UserIntent = Field(..., description="识别到的意图")
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    entities: Dict[str, Any] = Field(
        default_factory=dict,
        description="提取的实体信息"
    )
    reasoning: Optional[str] = Field(None, description="推理过程")
    high_intent: bool = Field(default=False, description="是否表现出强烈购买意向")


class QuoteParams(BaseModel):
    """报价单参数"""
    customer_name: str = Field(..., description="客户名称")
    products: List[Dict[str, Any]] = Field(..., description="产品列表")
    valid_days: int = Field(default=30, description="有效期（天）")
    discount_rate: Optional[float] = Field(None, ge=0, le=1, description="折扣率")
    notes: Optional[str] = Field(None, description="备注")


class ProposalParams(BaseModel):
    """提案书参数"""
    customer_name: str = Field(..., description="客户名称")
    project_name: str = Field(..., description="项目名称")
    project_background: Optional[str] = Field(None, description="项目背景")
    solution_highlights: List[str] = Field(default_factory=list, description="方案亮点")
    timeline: Optional[str] = Field(None, description="实施周期")
    budget_range: Optional[str] = Field(None, description="预算范围")


class ContractParams(BaseModel):
    """合同参数"""
    party_a: str = Field(..., description="甲方名称")
    party_b: str = Field(..., description="乙方名称")
    contract_type: str = Field(..., description="合同类型")
    key_terms: Dict[str, Any] = Field(default_factory=dict, description="关键条款")
    amount: Optional[float] = Field(None, description="合同金额")


class AnalysisParams(BaseModel):
    """数据分析参数"""
    data_source: str = Field(..., description="数据源描述或文件路径")
    analysis_type: str = Field(..., description="分析类型")
    metrics: List[str] = Field(default_factory=list, description="关键指标")
    date_range: Optional[str] = Field(None, description="时间范围")


class PresentationParams(BaseModel):
    """演示文稿参数"""
    title: str = Field(..., description="演示标题")
    subtitle: Optional[str] = Field(None, description="副标题")
    sections: List[str] = Field(default_factory=list, description="章节大纲")
    target_audience: Optional[str] = Field(None, description="目标受众")
    slides_count: int = Field(default=10, ge=3, le=50, description="幻灯片数量")
