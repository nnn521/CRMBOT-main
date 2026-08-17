"""
LangGraph State 定义 - 工作流状态的数据结构

这是整个 Agent 工作流的核心数据结构，贯穿所有节点。
每个节点读取和更新 State 中的字段来完成任务。

多模态升级（第一阶段）：
- 新增 input_image_url: 接收用户上传的汽车图片
- 新增 generated_media: 存储生成的汽车图片/试驾视频链接
"""

from typing import Annotated, Any, Dict, List, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

from app.models.chat import (
    AnalysisParams,
    ContractParams,
    DocumentInfo,
    IntentAnalysisResult,
    PresentationParams,
    ProposalParams,
    QuoteParams,
    UserIntent,
)


class SalesState(TypedDict):
    """
    销售 AI Agent 的工作流状态（多模态汽车金牌销售顾问版）
    
    字段说明：
    - messages: 对话历史（使用 add_messages 合并器自动追加）
    - session_id: 会话唯一标识
    - intent_analysis: 意图分析结果
    - context: 业务上下文（客户信息、产品信息等）
    - knowledge_results: RAG 检索结果
    - document_params: 文档生成参数
    - generated_documents: 已生成的文档列表
    - sales_response: 最终销售回复内容
    - next_node: 下一个要执行的节点
    - error: 错误信息
    - metadata: 额外的元数据
    
    【多模态新增字段】
    - input_image_url: 用户上传的汽车图片 URL（用于车型识别、外观分析）
    - generated_media: AI 生成的定制化汽车图片或动态试驾视频链接列表
    """
    
    # 对话相关
    messages: Annotated[list, add_messages]
    session_id: str
    
    # 意图和上下文
    intent_analysis: Optional[IntentAnalysisResult]
    context: Dict[str, Any]
    
    # RAG 检索结果
    knowledge_results: List[Dict[str, Any]]
    images: List[str]
    
    # 文档生成相关
    document_params: Optional[Dict[str, Any]]
    generated_documents: List[DocumentInfo]
    
    # 输出结果
    sales_response: Optional[str]
    suggested_actions: List[str]
    
    # 工作流控制
    next_node: Optional[str]
    error: Optional[str]
    metadata: Dict[str, Any]
    
    # ═══════════════════════════════════════════════════════════════
    # 【多模态汽车金牌销售顾问 - 新增字段】
    # ═══════════════════════════════════════════════════════════════
    # 用户输入：汽车图片 URL（用于车型识别、外观分析、配置咨询）
    input_image_url: Optional[str]
    
    # AI 生成输出：定制化汽车图片/动态试驾视频链接列表
    # 示例：["https://xxx.com/custom-car-red.jpg", "https://xxx.com/test-drive-video.mp4"]
    generated_media: Annotated[List[str], lambda x, y: x + y if y else x]


class DocumentState(BaseModel):
    """
    文档生成专用状态 - 用于文档生成子图
    
    这个状态专门用于处理文档生成工作流，
    与主 State 通过 document_params 字段关联。
    """
    
    doc_type: str = Field(..., description="文档类型")
    params: Dict[str, Any] = Field(..., description="文档参数")
    template_path: Optional[str] = Field(None, description="模板文件路径")
    output_path: Optional[str] = Field(None, description="输出文件路径")
    status: str = Field(default="pending", description="状态: pending/processing/completed/failed")
    error_msg: Optional[str] = Field(None, description="错误信息")
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


class KnowledgeState(BaseModel):
    """
    知识库检索专用状态 - 用于 RAG 子图
    """
    
    query: str = Field(..., description="检索查询")
    filters: Dict[str, Any] = Field(default_factory=dict, description="过滤条件")
    top_k: int = Field(default=5, description="返回结果数量")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="检索结果")
    relevance_score: float = Field(default=0.0, description="相关度分数")


def create_initial_state(
    session_id: str,
    user_message: str,
    context: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict]] = None,
    input_image_url: Optional[str] = None
) -> SalesState:
    """
    创建初始状态（多模态版）
    
    Args:
        session_id: 会话ID
        user_message: 用户当前消息
        context: 业务上下文
        history: 历史消息列表
        input_image_url: 用户上传的汽车图片 URL（多模态新增）
    
    Returns:
        初始化后的 SalesState
    """
    messages = history or []
    messages.append({"role": "user", "content": user_message})
    
    return SalesState(
        messages=messages,
        session_id=session_id,
        intent_analysis=None,
        context=context or {},
        knowledge_results=[],
        images=[],
        generated_documents=[],
        sales_response=None,
        suggested_actions=[],
        next_node="intent_recognition",
        error=None,
        metadata={},
        # 多模态字段初始化
        input_image_url=input_image_url,
        generated_media=[]
        # 注意：document_params 不重置，由 checkpoint 保留以支持多轮文档参数补充
    )
