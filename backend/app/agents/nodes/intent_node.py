"""
意图识别节点 - 分析用户输入，确定销售场景

重构要点：
1. 三层 JSON 回退解析（标准 → Markdown代码块 → 正则提取）
2. Pydantic 兜底：任何解析失败返回默认意图，绝不 500
3. 状态字典净化：不放入 missing_params，下游节点直接赋默认值
4. 防御性编程：LLM 调用失败有兜底，空消息有处理

【多模态汽车金牌销售顾问升级】
- 重写 System Prompt：保时捷/比亚迪金牌销售人设
- 新增意图：analyze_car_image（分析汽车图片）、generate_custom_car（生成定制效果图/视频）
"""

import json
import re
from typing import Dict, Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logging import get_logger
from app.agents.state import SalesState
from app.models.chat import IntentAnalysisResult, UserIntent

logger = get_logger("intent_node")


# ═══════════════════════════════════════════════════════════════
# 默认意图配置（Pydantic 兜底用）
# ═══════════════════════════════════════════════════════════════

DEFAULT_INTENT_ANALYSIS = IntentAnalysisResult(
    intent=UserIntent.GENERAL_CHAT,
    confidence=0.5,
    entities={},
    reasoning="解析失败，使用默认意图",
    high_intent=False,
)

# 强意向触发关键词
HIGH_INTENT_KEYWORDS = [
    "今天能定", "马上提车", "立刻下单", "现在就买", "有没有现车",
    "今天提", "马上付款", "全款", "刷卡", "帮我留着", "定金",
    "今天订", "现在定", "马上定", "我要买", "就这台", "就选这个",
    "不用考虑了", "就要这个", "直接签", "什么时候能提",
]


# ═══════════════════════════════════════════════════════════════
# 三层 JSON 回退解析（核心防御机制）
# ═══════════════════════════════════════════════════════════════

def safe_parse_json(raw_text: str) -> Dict[str, Any]:
    """
    三层 JSON 回退解析函数
    
    无论 LLM 返回什么格式，都尝试提取有效 JSON：
    1. 标准 JSON 解析
    2. Markdown 代码块提取（```json ... ```）
    3. 裸 JSON 对象正则提取
    4. 兜底返回默认结构
    
    Args:
        raw_text: LLM 返回的原始文本
        
    Returns:
        解析后的字典（绝不抛异常）
    """
    if not raw_text or not isinstance(raw_text, str):
        logger.warning("[JSON Parse] 输入为空或非字符串")
        return {}
    
    raw_text = raw_text.strip()
    if not raw_text:
        return {}
    
    # ═══ 第一层：标准 JSON 解析 ═══
    try:
        result = json.loads(raw_text)
        if isinstance(result, dict):
            logger.debug("[JSON Parse] 标准解析成功")
            return result
    except json.JSONDecodeError:
        pass
    
    # ═══ 第二层：Markdown 代码块提取 ═══
    # 匹配 ```json ... ``` 或 ``` ... ```
    md_patterns = [
        r'```json\s*(.*?)\s*```',  # 带 json 标记
        r'```\s*(.*?)\s*```',       # 无语言标记
    ]
    
    for pattern in md_patterns:
        matches = re.findall(pattern, raw_text, re.DOTALL | re.IGNORECASE)
        for match in matches:
            try:
                result = json.loads(match.strip())
                if isinstance(result, dict):
                    logger.debug(f"[JSON Parse] Markdown代码块解析成功 (pattern: {pattern[:20]}...)")
                    return result
            except json.JSONDecodeError:
                continue
    
    # ═══ 第三层：裸 JSON 对象正则提取 ═══
    # 匹配最外层的大括号结构（支持嵌套）
    # 使用非贪婪匹配，但要处理嵌套情况
    json_patterns = [
        # 匹配 { ... }，支持嵌套一层
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        # 更宽松的模式：从第一个 { 到最后一个 }
        r'\{.*\}',
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, raw_text, re.DOTALL)
        # 按长度降序，优先尝试更长的匹配（更可能是完整 JSON）
        matches.sort(key=len, reverse=True)
        
        for match in matches:
            try:
                result = json.loads(match.strip())
                if isinstance(result, dict):
                    logger.debug(f"[JSON Parse] 正则提取成功 (长度: {len(match)})")
                    return result
            except json.JSONDecodeError:
                continue
    
    # ═══ 兜底：返回空字典 ═══
    logger.warning(f"[JSON Parse] 所有解析方式失败，返回空字典。原始文本前100字符: {raw_text[:100]}...")
    return {}


def parse_intent_from_dict(data: Dict[str, Any]) -> IntentAnalysisResult:
    """
    将字典解析为 IntentAnalysisResult
    
    防御性处理：
    - 字段缺失使用默认值
    - 类型错误使用默认值
    - 无效枚举值使用默认值
    
    Args:
        data: 解析后的字典
        
    Returns:
        IntentAnalysisResult（绝不抛异常）
    """
    if not isinstance(data, dict):
        logger.warning(f"[Intent Parse] 输入非字典: {type(data)}")
        return DEFAULT_INTENT_ANALYSIS
    
    try:
        # 提取 intent（防御性）
        intent_raw = data.get("intent", "general_chat")
        intent_str = str(intent_raw).lower().strip() if intent_raw else "general_chat"
        
        # 验证 intent 是否在枚举中
        try:
            intent = UserIntent(intent_str)
        except ValueError:
            # 无效的 intent 值，使用关键词回退匹配
            intent = _fallback_intent_matching(intent_str, data)
        
        # 提取 confidence（防御性）
        confidence_raw = data.get("confidence", 0.5)
        try:
            confidence = float(confidence_raw)
            confidence = max(0.0, min(1.0, confidence))  # 限制在 0-1 范围
        except (ValueError, TypeError):
            confidence = 0.5
        
        # 提取 entities（防御性）
        entities_raw = data.get("entities", {})
        if isinstance(entities_raw, dict):
            entities = entities_raw
        else:
            entities = {}
        
        # 提取 reasoning（防御性）
        reasoning_raw = data.get("reasoning", "")
        reasoning = str(reasoning_raw) if reasoning_raw else ""

        # 提取 high_intent（防御性）
        high_intent_raw = data.get("high_intent", False)
        high_intent = bool(high_intent_raw) if isinstance(high_intent_raw, (bool, int, str)) else False

        return IntentAnalysisResult(
            intent=intent,
            confidence=confidence,
            entities=entities,
            reasoning=reasoning,
            high_intent=high_intent,
        )
        
    except Exception as e:
        logger.error(f"[Intent Parse] 解析异常: {e}")
        return DEFAULT_INTENT_ANALYSIS


def _fallback_intent_matching(intent_str: str, data: Dict) -> UserIntent:
    """
    意图回退匹配 - 当 LLM 返回的 intent 不在枚举中时
    
    使用关键词匹配进行兜底
    """
    intent_keywords = {
        UserIntent.QUOTE_GENERATION: ["报价", "quotation", "quote", "价格清单", "报价单"],
        UserIntent.PROPOSAL_CREATION: ["提案", "proposal", "方案", "建议书", "项目建议"],
        UserIntent.CONTRACT_DRAFTING: ["合同", "contract", "协议", "agreement", "条款", "分期", "贷款", "按揭", "金融"],
        UserIntent.PRESENTATION_REQUEST: ["ppt", "演示", "presentation", "幻灯片", "pitch", "讲演"],
        UserIntent.DATA_ANALYSIS: ["报表", "分析", "统计", "excel", "数据", "analytics"],
        UserIntent.PRICE_NEGOTIATION: ["折扣", "优惠", "便宜", "降价", "价格太贵", "negotiation"],
        UserIntent.COMPLAINT_HANDLING: ["投诉", "不满意", "退款", "complaint", "糟糕", "问题"],
        UserIntent.PRODUCT_INQUIRY: ["产品", "功能", "怎么用", "规格", "介绍", "inquiry"],
        UserIntent.FOLLOW_UP: ["跟进", "进度", "催促", "follow", "status"],
        # 【多模态汽车金牌销售顾问 - 新增关键词】
        UserIntent.ANALYZE_CAR_IMAGE: ["图片", "照片", "车型", "外观", "颜色", "这是", "什么车", "image", "photo", "picture"],
        UserIntent.GENERATE_CUSTOM_CAR: ["定制", "效果图", "试驾视频", "配置", "轮毂", "车漆", "custom", "render", "video"],
    }
    
    combined_text = intent_str.lower()
    
    # 检查 entities 中是否有线索
    entities = data.get("entities", {})
    if isinstance(entities, dict):
        for key in entities.keys():
            combined_text += " " + str(key).lower()
    
    best_intent = UserIntent.GENERAL_CHAT
    max_matches = 0
    
    for intent, keywords in intent_keywords.items():
        matches = sum(1 for kw in keywords if kw in combined_text)
        if matches > max_matches:
            max_matches = matches
            best_intent = intent
    
    logger.debug(f"[Intent Fallback] 关键词匹配: {intent_str} -> {best_intent.value} ({max_matches} 个匹配)")
    return best_intent


# ═══════════════════════════════════════════════════════════════
# 【多模态汽车金牌销售顾问 - System Prompt】
# ═══════════════════════════════════════════════════════════════

INTENT_PROMPT = """你是一位丰田汽车销售顾问的意图识别专家，负责分析客户输入并确定其真实意图。

【可选的意图类别】
- general_chat: 普通闲聊（问候、感谢、告别等）
- product_inquiry: 产品咨询（询问车型、配置、性能、价格、落地价、有什么车型等）
- price_negotiation: 价格谈判（要求打折、砍价、嫌贵、要优惠、问能不能便宜等）
- document_request: 请求生成文档（未明确具体类型）
- quote_generation: 生成报价单（明确提到报价单、报价、价格清单等）
- proposal_creation: 创建方案/提案（提到方案、建议书、推荐等）
- contract_drafting: 起草合同（提到合同、协议、条款等）
- data_analysis: 数据分析/报表（提到报表、分析、统计数据等）
- presentation_request: 请求演示文稿（提到PPT、演示、介绍资料等）
- complaint_handling: 投诉处理（表达不满、投诉、退款要求等）
- follow_up: 跟进提醒（询问进度、催促回复等）
- analyze_car_image: 分析汽车图片（用户发送或上传汽车图片时触发）
- generate_custom_car: 生成定制效果图/视频时触发

请输出 JSON 格式（直接输出纯 JSON，不要 Markdown 标记）：
{
    "intent": "意图类别",
    "confidence": 0.95,
    "entities": {
        "customer_name": "客户名称（如有）",
        "product_name": "产品名称（如车型、型号等）",
        "budget_range": "预算范围（如有）",
        ...其他提取的实体
    },
    "reasoning": "简要的推理过程",
    "high_intent": false
}

关键识别规则：
1. 客户问"你有哪些车型"、"凯美瑞多少钱"、"落地价多少" → product_inquiry（问价不等于谈判）
2. 客户说"太贵了"、"能便宜点吗"、"最低多少"、"有优惠吗" → price_negotiation
3. 客户问"你是谁" → general_chat
4. 客户明确要"报价单"/"价格单" → quote_generation
5. 客户提到"签约"、"合同"、"起草"、"协议" → contract_drafting
6. 客户提到"金融分期"、"贷款"、"按揭"、"办分期"、"36期"、"24期" → contract_drafting（金融分期合同），不要识别为 proposal_creation
7. 客户提到"提案"、"方案书"、"建议书" → proposal_creation
8. 客户提到"预约"、"服务"、"试驾"、"售后"、"保养"、"维修"、"到店" → service_appointment
9. 当客户表达强烈购买意向时，设置 high_intent 为 true。触发词包括但不限于：
   "今天能定"、"马上提车"、"立刻下单"、"现在就买"、"有没有现车"、"今天提"、
   "马上付款"、"全款"、"刷卡"、"帮我留着"、"定金"、"不用考虑了"、"就要这个"、
   "直接签"、"什么时候能提"
10. 直接输出 JSON，不要添加 ```json 标记"""


# ═══════════════════════════════════════════════════════════════
# 路由决策函数
# ═══════════════════════════════════════════════════════════════

def determine_next_node(intent: UserIntent) -> str:
    """
    根据意图决定下一个节点
    
    路由规则：
    - 产品咨询 -> 知识库检索
    - 文档相关 -> 文档生成参数提取（强制跳过询问，下游赋默认值）
    - 价格谈判 -> 销售话术
    - 多模态图片分析 -> 图片分析节点
    - 多模态生成 -> 媒体生成节点
    - 其他 -> 直接响应
    
    Args:
        intent: 识别到的用户意图
        
    Returns:
        下一个节点名称
    """
    routing_map = {
        UserIntent.PRODUCT_INQUIRY: "knowledge_retrieval",
        UserIntent.QUOTE_GENERATION: "extract_document_params",
        UserIntent.PROPOSAL_CREATION: "extract_document_params",
        UserIntent.CONTRACT_DRAFTING: "extract_document_params",
        UserIntent.DATA_ANALYSIS: "extract_document_params",
        UserIntent.PRESENTATION_REQUEST: "extract_document_params",
        UserIntent.DOCUMENT_REQUEST: "extract_document_params",
        UserIntent.PRICE_NEGOTIATION: "sales_negotiation",
        UserIntent.COMPLAINT_HANDLING: "complaint_handler",
        # 【多模态汽车金牌销售顾问 - 新增路由】
        UserIntent.ANALYZE_CAR_IMAGE: "analyze_car_image",      # 图片分析节点
        UserIntent.GENERATE_CUSTOM_CAR: "generate_custom_car",  # 媒体生成节点
        UserIntent.SERVICE_APPOINTMENT: "sales_response",     # 预约线下服务 → 对话引导
    }
    
    next_node = routing_map.get(intent, "sales_response")
    logger.info(f"[Routing] 意图 {intent.value} -> 节点 {next_node}")
    return next_node


# ═══════════════════════════════════════════════════════════════
# LangGraph 节点函数
# ═══════════════════════════════════════════════════════════════

async def intent_recognition_node(state: SalesState) -> SalesState:
    """
    意图识别节点 - 防御性增强版（多模态汽车金牌销售顾问）
    
    核心流程：
    1. 获取用户消息（防御性处理空消息）
    2. 检查是否有图片上传（多模态新增）
    3. 调用 LLM 进行意图识别
    4. 三层 JSON 解析
    5. Pydantic 验证 + 兜底
    6. 输出纯净 State（含 next_node 路由决策）
    
    保证：
    - 绝不抛出异常
    - 返回的 State 总是有效字典
    - intent_analysis 总是 IntentAnalysisResult 类型
    """
    session_id = state.get("session_id", "unknown")
    logger.info(f"[Session: {session_id}] 开始意图识别")

    # ═══ 清除上一轮的回复和文档，防止 checkpoint 持久化导致旧数据复用 ═══
    # 注意：保留 document_params 以支持多轮合同/提案参数补充
    state["sales_response"] = None
    state["generated_documents"] = []
    state["suggested_actions"] = []

    # ═══ 防御性：获取用户消息 ═══
    user_message = ""
    try:
        messages = state.get("messages", [])
        if messages and isinstance(messages, list):
            last_message = messages[-1]
            if hasattr(last_message, 'content'):
                user_message = last_message.content or ""
            elif isinstance(last_message, dict):
                user_message = last_message.get('content', '')
            else:
                user_message = str(last_message)
    except Exception as e:
        logger.warning(f"[Intent] 获取用户消息失败: {e}")
        user_message = ""
    
    user_message = user_message.strip() if user_message else ""
    
    # ═══ 多模态：检查是否有图片上传 ═══
    input_image_url = state.get("input_image_url")
    if input_image_url:
        logger.info(f"[Intent] 检测到用户上传图片: {input_image_url}")
        # 如果有图片但消息为空或简短，补充提示
        if not user_message or len(user_message) < 5:
            user_message = user_message + " [用户上传了汽车图片，请分析车型和外观]"
    
    # 空消息处理
    if not user_message:
        logger.warning("[Intent] 用户消息为空，使用默认意图")
        state["intent_analysis"] = DEFAULT_INTENT_ANALYSIS
        state["next_node"] = "sales_response"
        state["context"] = state.get("context", {})
        return state
    
    # ═══ 调用 LLM 进行意图识别 ═══
    try:
        llm = ChatOpenAI(
            model=settings.default_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.2,  # 低温度以获得更确定的结果
        )
        
        messages = [
            SystemMessage(content=INTENT_PROMPT),
            HumanMessage(content=f"请分析以下客户消息：\n\n{user_message}")
        ]
        
        response = await llm.ainvoke(messages)
        raw_response = response.content if hasattr(response, 'content') else str(response)
        
        logger.debug(f"[Intent] LLM 原始响应: {raw_response[:200]}...")
        
    except Exception as e:
        logger.error(f"[Intent] LLM 调用失败: {e}")
        # LLM 调用失败，使用兜底解析
        state["intent_analysis"] = _fallback_keyword_intent(user_message)
        state["next_node"] = determine_next_node(state["intent_analysis"].intent)
        state["context"] = _extract_entities_from_message(state.get("context", {}), user_message)
        return state
    
    # ═══ 三层 JSON 解析 ═══
    parsed_dict = safe_parse_json(raw_response)
    
    # ═══ Pydantic 验证（带兜底）═══
    if parsed_dict:
        intent_analysis = parse_intent_from_dict(parsed_dict)
    else:
        # 解析彻底失败，使用关键词回退
        intent_analysis = _fallback_keyword_intent(user_message)
    
    # 【多模态增强】如果有图片上传，优先考虑图片相关意图
    if input_image_url and intent_analysis.intent in [UserIntent.GENERAL_CHAT, UserIntent.UNKNOWN]:
        logger.info("[Intent] 用户上传了图片，但意图不明确， fallback 到 analyze_car_image")
        intent_analysis = IntentAnalysisResult(
            intent=UserIntent.ANALYZE_CAR_IMAGE,
            confidence=0.8,
            entities={"image_url": input_image_url, **intent_analysis.entities},
            reasoning="用户上传了汽车图片，需要分析车型和外观"
        )
    
    # ═══ 高意向关键词补充检测 ═══
    # 即使 LLM 未标记 high_intent，只要消息包含强意向关键词就标记
    if not intent_analysis.high_intent:
        message_lower = user_message.lower()
        for kw in HIGH_INTENT_KEYWORDS:
            if kw in message_lower:
                intent_analysis = IntentAnalysisResult(
                    intent=intent_analysis.intent,
                    confidence=intent_analysis.confidence,
                    entities=intent_analysis.entities,
                    reasoning=intent_analysis.reasoning,
                    high_intent=True,
                )
                logger.info(f"[Intent] 关键词触发高意向: {kw}")
                break

    logger.info(f"[Intent] 识别结果: {intent_analysis.intent.value}, 置信度: {intent_analysis.confidence:.2f}, 高意向: {intent_analysis.high_intent}")
    
    # ═══ 提取实体到 context（纯净字典）═══
    context = state.get("context", {})
    if not isinstance(context, dict):
        context = {}
    
    # 合并识别到的实体
    if intent_analysis.entities and isinstance(intent_analysis.entities, dict):
        context.update(intent_analysis.entities)
    
    # 额外提取：从消息中提取可能的客户名、车型等
    context = _extract_entities_from_message(context, user_message)
    
    # 【多模态】将图片 URL 保存到 context
    if input_image_url:
        context["input_image_url"] = input_image_url
    
    # ═══ 组装输出 State（纯净字典）═══
    state["intent_analysis"] = intent_analysis
    state["context"] = context
    state["next_node"] = determine_next_node(intent_analysis.intent)
    
    # 确保 metadata 存在
    if "metadata" not in state or not isinstance(state["metadata"], dict):
        state["metadata"] = {}
    
    # 记录调试信息
    state["metadata"]["intent_recognition"] = {
        "raw_response_preview": raw_response[:200] if len(raw_response) > 200 else raw_response,
        "parsed_success": bool(parsed_dict),
        "confidence": intent_analysis.confidence,
        "has_image": bool(input_image_url),
    }
    
    return state


def _fallback_keyword_intent(user_message: str) -> IntentAnalysisResult:
    """
    关键词回退意图识别 - 当 LLM 完全失败时使用
    """
    message_lower = user_message.lower()
    
    intent_keywords = {
        UserIntent.QUOTE_GENERATION: ["报价", "报价单", "价格清单", "quotation", "quote", "多少钱", "费用", "落地价"],
        UserIntent.PROPOSAL_CREATION: ["提案", "方案", "建议书", "proposal", "项目建议", "解决方案", "购车方案"],
        UserIntent.CONTRACT_DRAFTING: ["合同", "协议", "contract", "agreement", "条款", "签约", "预订", "分期", "贷款", "按揭", "金融"],
        UserIntent.PRESENTATION_REQUEST: ["ppt", "演示", "幻灯片", "presentation", "pitch", "讲演", "汇报", "资料"],
        UserIntent.DATA_ANALYSIS: ["报表", "分析", "统计", "excel", "数据", "analytics", "报表", "对比数据"],
        UserIntent.PRICE_NEGOTIATION: ["折扣", "优惠", "便宜", "降价", "价格太贵", "negotiation", "能不能便宜", "分期", "金融方案"],
        UserIntent.COMPLAINT_HANDLING: [
            "投诉", "不满意", "退款", "complaint", "糟糕", "问题", "差评", "服务差",
            "质量太差", "态度太差", "交车延迟", "还没交车", "刚买完就降价", "欺骗",
            "售后维修", "排队", "我要投诉",
        ],
        UserIntent.PRODUCT_INQUIRY: ["产品", "车型", "功能", "怎么用", "规格", "介绍", "inquiry", "有什么功能", "有哪些", "续航", "百公里加速", "内饰", "配置"],
        UserIntent.FOLLOW_UP: ["跟进", "进度", "催促", "follow", "status", "怎么样了", "试驾预约", "到店"],
        # 【多模态汽车金牌销售顾问 - 新增关键词】
        UserIntent.ANALYZE_CAR_IMAGE: ["图片", "照片", "外观", "颜色", "这是", "什么车", "image", "photo", "picture", "看看这车", "帮我看看"],
        UserIntent.GENERATE_CUSTOM_CAR: ["定制", "效果图", "试驾视频", "配置", "轮毂", "车漆", "custom", "render", "video", "看看效果", "动态视频", "加速视频"],
        UserIntent.SERVICE_APPOINTMENT: ["预约", "服务", "试驾", "到店", "售后", "保养", "维修", "检测", "检修", "appointment", "线下", "门店", "4s店"],
    }
    
    best_intent = UserIntent.GENERAL_CHAT
    max_matches = 0
    
    for intent, keywords in intent_keywords.items():
        matches = sum(1 for kw in keywords if kw in message_lower)
        if matches > max_matches:
            max_matches = matches
            best_intent = intent
    
    confidence = min(0.5 + max_matches * 0.1, 0.7)
    
    logger.info(f"[Intent Fallback] 关键词匹配: {best_intent.value} (置信度: {confidence:.2f})")

    # 检测高意向关键词
    high_intent = any(kw in message_lower for kw in HIGH_INTENT_KEYWORDS)

    return IntentAnalysisResult(
        intent=best_intent,
        confidence=confidence,
        entities={},
        reasoning=f"基于关键词回退匹配 ({max_matches} 个匹配)",
        high_intent=high_intent,
    )


def _extract_entities_from_message(context: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    """
    从用户消息中直接提取实体信息
    
    作为 LLM 实体提取的补充/兜底（多模态汽车金牌销售顾问版）
    """
    if not isinstance(context, dict):
        context = {}
    
    message = user_message.lower()
    
    # 提取客户名称（常见的"我是XX"、"XX公司"等模式）
    if "customer_name" not in context or not context["customer_name"]:
        name_patterns = [
            r'我是(\S+?)(?:的|先生|女士|，|。|$)',
            r'(\S+?)(?:先生|女士)(?:想|要|咨询)',
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message)
            if match:
                context["customer_name"] = match.group(1).strip()
                break
    
    # 【多模态汽车】提取车型名称
    if "car_model" not in context or not context["car_model"]:
        # 常见车型关键词
        car_patterns = [
            r'(保时捷\s*\d{3}|保时捷\s*[a-zA-Z]+|比亚迪\s*\S+|汉\s*EV|唐\s*DM|海豹|海豚|海鸥|911|卡宴|帕拉梅拉|taycan)',
            r'(\d{3})[^\d]?',  # 911, 718 等
        ]
        for pattern in car_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                context["car_model"] = match.group(1).strip()
                break
    
    # 【多模态汽车】提取颜色偏好
    if "color_preference" not in context or not context["color_preference"]:
        color_keywords = ["冰莓粉", "午夜蓝", "勃艮第红", "哑灰", "白色", "黑色", "红色", "蓝色", "银色", "灰色", "绿色"]
        for color in color_keywords:
            if color in message:
                context["color_preference"] = color
                break
    
    # 【多模态汽车】提取配置关键词
    if "configuration" not in context or not context["configuration"]:
        config_keywords = ["运动轮毂", "红色卡钳", "真皮座椅", "全景天窗", "自动驾驶", "空气悬架", "柏林之声", "bose音响"]
        matched_configs = [kw for kw in config_keywords if kw in message]
        if matched_configs:
            context["configuration"] = ", ".join(matched_configs)
    
    # 提取预算范围
    if "budget_range" not in context or not context["budget_range"]:
        budget_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:万|w|万元)',
            r'预算[\s约]*(\d+(?:\.\d+)?)',
        ]
        for pattern in budget_patterns:
            match = re.search(pattern, message)
            if match:
                try:
                    budget = float(match.group(1))
                    context["budget_range"] = f"{budget}万"
                    break
                except ValueError:
                    pass
    
    return context


# ═══════════════════════════════════════════════════════════════
# 兼容导出（旧代码可能依赖的函数）
# ═══════════════════════════════════════════════════════════════

# 保留旧函数名兼容性
_fallback_intent_parsing = _fallback_keyword_intent
_determine_next_node = determine_next_node
