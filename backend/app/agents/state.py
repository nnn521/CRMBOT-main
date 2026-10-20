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
    citations: List[Dict[str, Any]]
    knowledge_release_id: Optional[str]
    answer_status: Optional[str]
    data_as_of: Optional[str]
    assumptions: List[str]
    limitations: List[str]
    
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


def strip_messages(state: SalesState) -> SalesState:
    """
    从节点返回的状态中移除 messages 键。

    messages 通道使用 add_messages 合并器：节点返回完整状态时会把它整体
    再次追加到 checkpoint 消息上，造成每条消息在每个节点重复一遍。
    非终态节点必须用本函数剥离 messages 后再返回。
    """
    state.pop("messages", None)
    return state


def state_update_with_reply(state: SalesState, reply: str) -> Dict[str, Any]:
    """
    终态节点统一输出：剥离全量 messages，仅追加本条回复为一条 AIMessage，
    同时写入 sales_response。其余键原样携带（与 checkpoint 合并）。
    """
    from langchain_core.messages import AIMessage

    update = {k: v for k, v in state.items() if k != "messages"}
    update["sales_response"] = reply
    update["messages"] = [AIMessage(content=reply)]
    return update


def create_initial_state(
    session_id: str,
    user_message: str,
    context: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict]] = None,
    input_image_url: Optional[str] = None
) -> SalesState:
    """
    创建初始状态（多模态版）

    注意（历史修复）：
    - chat API 不再传 history：跨轮对话由 LangGraph checkpoint 维护。
      传入 history 会经 add_messages 与 checkpoint 合并，导致消息重复膨胀，
      因此该参数仅用于无 checkpoint 的直接调用（如单元测试）。
    - context 仅在显式提供时才包含在输入中；不提供时保留 checkpoint
      里积累的多轮上下文（客户名、车型等）。

    Args:
        session_id: 会话ID
        user_message: 用户当前消息
        context: 业务上下文（可选；不传则沿用 checkpoint 上下文）
        history: 【已废弃】历史消息列表，仅用于无 checkpoint 的直接调用
        input_image_url: 用户上传的汽车图片 URL（多模态新增）

    Returns:
        初始化后的 SalesState
    """
    messages = list(history) if history else []
    messages.append({"role": "user", "content": user_message})

    state: SalesState = SalesState(
        messages=messages,
        session_id=session_id,
        intent_analysis=None,
        context=context if context is not None else {},
        knowledge_results=[],
        images=[],
        citations=[],
        knowledge_release_id=None,
        answer_status=None,
        data_as_of=None,
        assumptions=[],
        limitations=[],
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

    # context 为 None 时从输入中移除该键，让 checkpoint 中积累的上下文延续。
    if context is None:
        state.pop("context", None)

    return state
