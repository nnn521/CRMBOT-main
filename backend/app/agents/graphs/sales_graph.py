"""
销售 AI Agent 主工作流图 - LangGraph 编排（PostgreSQL 持久化版）

重构要点：
1. 将 MemorySaver 迁移至 AsyncPostgresSaver（PostgreSQL 持久化）
2. 双轨连接策略：初始化用 AsyncConnection，运行时用 AsyncConnectionPool
3. 禁用 Prepared Statement 缓存（兼容 Supabase 连接池）
4. 保留防御性编程：_sanitize_final_state 状态净化
"""

from typing import Dict, Any, Optional, Union

from langgraph.graph import StateGraph, END

# PostgreSQL 持久化相关导入
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.core.config import settings
from app.core.logging import get_logger
from app.agents.state import SalesState, create_initial_state
from app.agents.nodes.intent_node import intent_recognition_node
from app.agents.nodes.knowledge_node import (
    knowledge_retrieval_node,
    knowledge_synthesis_node,
)
from app.agents.nodes.document_nodes import (
    extract_document_params_node,
    generate_document_node,
)
from app.agents.nodes.response_node import (
    sales_response_node,
    sales_negotiation_node,
    complaint_handler_node,
)
from app.agents.nodes.multimodal_node import (
    vision_analysis_node,
    media_generation_node,
)

logger = get_logger("sales_graph")


# ═══════════════════════════════════════════════════════════════
# 工作流创建（纯工作流定义，无 checkpointer）
# ═══════════════════════════════════════════════════════════════

def _create_workflow() -> StateGraph:
    """
    创建销售 AI Agent 工作流图（纯定义，不编译）
    
    Returns:
        未编译的 StateGraph 实例
    """
    workflow = StateGraph(SalesState)
    
    # 添加节点
    workflow.add_node("intent_recognition", intent_recognition_node)
    workflow.add_node("knowledge_retrieval", knowledge_retrieval_node)
    workflow.add_node("knowledge_synthesis", knowledge_synthesis_node)
    workflow.add_node("extract_document_params", extract_document_params_node)
    workflow.add_node("generate_document", generate_document_node)
    workflow.add_node("sales_response", sales_response_node)
    workflow.add_node("sales_negotiation", sales_negotiation_node)
    workflow.add_node("complaint_handler", complaint_handler_node)
    # 【多模态】添加视觉分析和媒体生成节点
    workflow.add_node("vision_analysis", vision_analysis_node)
    workflow.add_node("media_generation", media_generation_node)
    
    # 设置入口点
    workflow.set_entry_point("intent_recognition")
    
    # 添加边和条件路由
    workflow.add_conditional_edges(
        "intent_recognition",
        _route_by_next_node,
        {
            "knowledge_retrieval": "knowledge_retrieval",
            "extract_document_params": "extract_document_params",
            "sales_negotiation": "sales_negotiation",
            "complaint_handler": "complaint_handler",
            # 【多模态】视觉分析和媒体生成路由
            "analyze_car_image": "vision_analysis",
            "generate_custom_car": "media_generation",
            "sales_response": "sales_response",
        }
    )
    
    workflow.add_conditional_edges(
        "knowledge_retrieval",
        _route_by_knowledge_result,
        {
            "knowledge_synthesis": "knowledge_synthesis",
            "sales_response": "sales_response",
        }
    )
    
    workflow.add_edge("knowledge_synthesis", "sales_response")
    workflow.add_edge("extract_document_params", "generate_document")
    workflow.add_edge("generate_document", END)
    # 【多模态】视觉分析和媒体生成直接结束
    workflow.add_edge("vision_analysis", END)
    workflow.add_edge("media_generation", END)
    # 销售回复后：如果有多轮对话中未完成的文档参数，继续走生成流程
    workflow.add_conditional_edges(
        "sales_response",
        _route_after_sales_response,
        {
            "extract_document_params": "extract_document_params",
            "end": END,
        }
    )
    workflow.add_edge("sales_negotiation", END)
    workflow.add_edge("complaint_handler", END)
    
    return workflow


def create_sales_graph() -> StateGraph:
    """
    创建销售 AI Agent 工作流图（内存存储版 - 向后兼容）
    
    注意：此函数保留用于向后兼容，实际运行时使用 run_sales_agent()
    它会使用 PostgreSQL 持久化。
    """
    from langgraph.checkpoint.memory import MemorySaver
    
    workflow = _create_workflow()
    checkpointer = MemorySaver()
    compiled_graph = workflow.compile(checkpointer=checkpointer)
    
    logger.info("销售 AI Agent 工作流图编译完成（内存存储版）")
    return compiled_graph


def _route_by_next_node(state: SalesState) -> str:
    """
    根据 state["next_node"] 路由到下一个节点
    """
    next_node = state.get("next_node")
    
    if next_node:
        logger.debug(f"[Router] 路由到节点: {next_node}")
        return next_node
    
    logger.warning("[Router] next_node 未设置，默认路由到 sales_response")
    return "sales_response"


def _route_after_sales_response(state: SalesState) -> str:
    """
    销售回复后路由：检查是否有多轮对话中未完成的文档生成任务

    当用户在合同/提案多轮对话中逐步提供信息时，
    即使当前消息意图不是 document_request，也需要继续生成流程。
    """
    doc_params = state.get("document_params")
    if doc_params and isinstance(doc_params, dict):
        missing = doc_params.get("missing", [])
        intent = doc_params.get("intent", "")
        if missing and intent in ("contract_drafting", "proposal_creation"):
            logger.info(f"[Router] 检测到未完成的文档生成 ({intent})，继续提取参数")
            return "extract_document_params"
    return "end"


def _route_by_knowledge_result(state: SalesState) -> str:
    """
    根据知识库检索结果路由
    """
    results = state.get("knowledge_results", [])
    
    if results and isinstance(results, list) and len(results) > 0:
        logger.debug(f"[Router] 检索到 {len(results)} 条知识，进入整合节点")
        return "knowledge_synthesis"
    
    logger.debug("[Router] 无知识检索结果，直接生成回复")
    return "sales_response"


# ═══════════════════════════════════════════════════════════════
# PostgreSQL 持久化 - 全局开关
# ═══════════════════════════════════════════════════════════════

# 全局标志：PostgreSQL 是否可用（由 initialize_database 设置）
_pg_available: bool = False

# 共享内存存储：跨请求保持 checkpoint（支持多轮文档参数补充）
from langgraph.checkpoint.memory import MemorySaver as _MemorySaver
_shared_memory_saver = _MemorySaver()


def is_pg_available() -> bool:
    """返回 PostgreSQL 是否已就绪"""
    return _pg_available


# ═══════════════════════════════════════════════════════════════
# PostgreSQL 持久化 - 数据库初始化
# ═══════════════════════════════════════════════════════════════

async def initialize_database() -> bool:
    global _pg_available
    """
    初始化数据库表结构 - 在应用启动时调用
    
    关键设计：
    1. 使用原生 AsyncConnection + autocommit=True（绕过事务块限制）
    2. 禁用 Prepared Statement 缓存（兼容 Supabase 连接池）
    3. 配置序列化器允许自定义类型反序列化
    
    Returns:
        bool: 初始化是否成功
    """
    if not settings.database_url:
        logger.warning("[Init] 未配置 DATABASE_URL，跳过数据库初始化")
        return False
    
    try:
        logger.info("[Init] 开始初始化 PostgreSQL 数据库...")
        
        # 关键 1：原生连接，非连接池
        # 关键 2：autocommit=True 绕过事务块（CREATE INDEX CONCURRENTLY 需要）
        # 关键 3：prepare_threshold=None 禁用 Prepared Statement（兼容 Supabase）
        # 关键 4：gssencmode="disable" 避免 GSSAPI 加密问题
        # 关键 5：添加连接超时，避免无限等待
        conn = await AsyncConnection.connect(
            settings.postgres_dsn,
            autocommit=True,
            gssencmode="disable",
            prepare_threshold=None,  # 禁用 Prepared Statement 缓存
            connect_timeout=15,  # 连接建立超时15秒
        )
        try:
            # 配置序列化器，允许自定义类型反序列化
            serde = JsonPlusSerializer(
                allowed_msgpack_modules=[
                    ("app.models.chat", "UserIntent"),
                    ("app.models.chat", "IntentAnalysisResult"),
                ]
            )
            checkpointer = AsyncPostgresSaver(conn, serde=serde)
            
            # 执行建表（包含 CREATE INDEX CONCURRENTLY）
            await checkpointer.setup()
            logger.info("[Init] 数据库表结构初始化完成")
        finally:
            await conn.close()
        
        _pg_available = True
        return True
    except Exception as e:
        logger.error(f"[Init] 数据库初始化失败: {e}")
        _pg_available = False
        return False


# ═══════════════════════════════════════════════════════════════
# PostgreSQL 持久化 - 运行时执行
# ═══════════════════════════════════════════════════════════════

async def run_sales_agent(
    session_id: str,
    message: str,
    context: dict = None,
    history: list = None
) -> Dict[str, Any]:
    """
    运行销售 AI Agent（PostgreSQL 持久化版）
    
    关键保证：
    1. 使用 PostgreSQL 持久化对话状态（跨会话记忆）
    2. 使用显式 AsyncConnectionPool 管理数据库连接
    3. 禁用 Prepared Statement 缓存（兼容 Supabase 连接池）
    4. 无论图怎么结束，都返回纯净 Dict
    5. 绝不触发 tuple index out of range
    
    Args:
        session_id: 会话唯一标识（用于状态隔离和恢复）
        message: 用户消息
        context: 业务上下文
        history: 历史消息
    
    Returns:
        最终状态字典（纯净 Dict，安全访问）
    """
    # 创建初始状态
    initial_state = create_initial_state(
        session_id=session_id,
        user_message=message,
        context=context,
        history=history
    )
    
    # 配置：thread_id 用于会话隔离和持久化
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": settings.max_iterations,
    }
    
    
    # ═══ 根据 PostgreSQL 可用性选择 checkpointer ═══
    final_state: Dict[str, Any] = {}
    
    try:
        if _pg_available:
            # PostgreSQL 持久化模式
            logger.info(f"[Session: {session_id}] 开始执行工作流（PostgreSQL 持久化）")
            async with AsyncConnectionPool(
                conninfo=settings.postgres_dsn,
                max_size=5,
                min_size=0,
                open=False,
                timeout=15,
                kwargs={
                    "prepare_threshold": None,
                    "connect_timeout": 10,
                },
            ) as pool:
                await pool.open(wait=True, timeout=10)
                
                serde = JsonPlusSerializer(
                    allowed_msgpack_modules=[
                        ("app.models.chat", "UserIntent"),
                        ("app.models.chat", "IntentAnalysisResult"),
                    ]
                )
                checkpointer = AsyncPostgresSaver(pool, serde=serde)
                workflow = _create_workflow()
                graph = workflow.compile(checkpointer=checkpointer)
                
                async for event in graph.astream(initial_state, config):
                    if not isinstance(event, dict):
                        continue
                    for node_name, state_value in event.items():
                        if isinstance(state_value, dict):
                            final_state = state_value
                        elif isinstance(state_value, (list, tuple)) and len(state_value) > 0:
                            first_item = state_value[0]
                            if isinstance(first_item, dict):
                                final_state = first_item
        else:
            # 内存模式（无 PostgreSQL）— 使用共享 MemorySaver 保持跨请求状态
            logger.info(f"[Session: {session_id}] 开始执行工作流（内存存储模式）")
            workflow = _create_workflow()
            graph = workflow.compile(checkpointer=_shared_memory_saver)
            
            async for event in graph.astream(initial_state, config):
                if not isinstance(event, dict):
                    continue
                for node_name, state_value in event.items():
                    if isinstance(state_value, dict):
                        final_state = state_value
                    elif isinstance(state_value, (list, tuple)) and len(state_value) > 0:
                        first_item = state_value[0]
                        if isinstance(first_item, dict):
                            final_state = first_item
        
        logger.info(f"[Session: {session_id}] 工作流执行完成")
        
    except Exception as e:
        logger.error(f"[Graph] 工作流执行异常: {e}")
        # 执行失败也返回兜底状态
        final_state = {
            "session_id": session_id,
            "sales_response": "抱歉，处理您的请求时出现了问题。请稍后重试。",
            "suggested_actions": ["重新尝试", "联系客服"],
            "error": str(e),
        }
    
    # ═══ 状态净化：确保所有字段有兜底值 ═══
    final_state = _sanitize_final_state(final_state, session_id)
    
    return final_state



# ═══════════════════════════════════════════════════════════════
# 防御性编程 - 状态净化
# ═══════════════════════════════════════════════════════════════

def _sanitize_final_state(state: Any, session_id: str) -> Dict[str, Any]:
    """
    净化最终状态：确保返回纯净 Dict，所有字段有兜底值
    
    这是防御 tuple 越界的核心函数。
    """
    # 如果 state 不是字典，创建新的
    if not isinstance(state, dict):
        logger.warning(f"[Sanitize] 状态非字典类型: {type(state)}，创建默认状态")
        state = {}
    
    # 确保关键字段存在且有有效值
    sanitized = {
        # 会话信息
        "session_id": state.get("session_id") or session_id,
        
        # 回复内容（绝不为 None）
        "sales_response": _safe_get_str(state, "sales_response", "处理完成，请查看相关文档。"),
        
        # 建议操作
        "suggested_actions": _safe_get_list(state, "suggested_actions"),
        
        # 生成的文档列表
        "generated_documents": _safe_get_list(state, "generated_documents"),
        
        # 意图分析（可能为 None，但字典结构安全）
        "intent_analysis": state.get("intent_analysis"),
        
        # 上下文
        "context": state.get("context") or {},
        
        # 知识检索结果
        "knowledge_results": _safe_get_list(state, "knowledge_results"),
        "images": _safe_get_list(state, "images"),
        
        # 对话历史
        "messages": _safe_get_list(state, "messages"),
        
        # 元数据
        "metadata": state.get("metadata") or {},
        
        # 错误信息（如果有）
        "error": state.get("error"),
    }
    
    return sanitized


def _safe_get_str(state: Dict, key: str, default: str = "") -> str:
    """安全获取字符串字段"""
    value = state.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _safe_get_list(state: Dict, key: str) -> list:
    """安全获取列表字段"""
    value = state.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


# ═══════════════════════════════════════════════════════════════
# 全局图实例（向后兼容）
# ═══════════════════════════════════════════════════════════════

_sales_graph = None


def get_sales_graph():
    """获取销售图单例（向后兼容）"""
    global _sales_graph
    if _sales_graph is None:
        _sales_graph = create_sales_graph()
    return _sales_graph


# ═══════════════════════════════════════════════════════════════
# 便捷函数：提取核心响应数据
# ═══════════════════════════════════════════════════════════════

def extract_response_data(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    从最终状态中提取前端需要的核心响应数据
    
    这是 API 层调用的辅助函数，确保字段安全。
    """
    return {
        "session_id": final_state.get("session_id", ""),
        "reply": final_state.get("sales_response", ""),
        "intent": final_state.get("intent_analysis", {}).get("intent", "unknown") if final_state.get("intent_analysis") else "unknown",
        "documents": [
            {
                "filename": doc.get("file_name", ""),
                "path": doc.get("file_path", ""),
                "type": doc.get("doc_type", ""),
                "size": doc.get("file_size", 0),
            }
            for doc in final_state.get("generated_documents", [])
            if isinstance(doc, dict)
        ],
        "suggested_actions": final_state.get("suggested_actions", []),
        "metadata": final_state.get("metadata", {}),
    }
