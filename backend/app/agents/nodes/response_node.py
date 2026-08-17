"""
销售回复节点 - 生成最终回复内容（重构版 - 多模态汽车金牌销售顾问）

这是工作流的最后一个节点，负责整合所有信息生成最终回复。
防御性设计：无论前面节点输出什么，都生成有效的回复。

【人设】丰田（广汽丰田/一汽丰田/进口丰田）金牌汽车销售顾问

【价格谈判 & 投诉处理】
- 加载 YAML 话术模板进行场景匹配
- 使用 LLM 生成个性化回复
- 多层兜底：LLM 失败 → YAML 模板 → 硬编码默认回复
"""

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logging import get_logger
from app.agents.state import SalesState
from app.models.chat import UserIntent

logger = get_logger("response_node")


# LLM 上下文窗口内保留的对话历史条数上限
MAX_CONTEXT_MESSAGES = 50

# YAML 话术模板路径（相对于 backend/ 目录）
NEGOTIATION_YAML_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "scripts" / "negotiation.yaml"
COMPLAINT_YAML_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "scripts" / "complaint.yaml"


# Issue #6: mtime-based cache (auto-reload on file change, no restart needed)
_yaml_cache: dict = {}  # {path_str: {"mtime": float, "data": dict}}


def _load_yaml_with_mtime_cache(yaml_path, label: str) -> Dict[str, Any]:
    """加载 YAML，基于文件修改时间自动重载"""
    key = str(yaml_path)
    try:
        if yaml_path.exists():
            mtime = yaml_path.stat().st_mtime
            cached = _yaml_cache.get(key)
            if cached and cached.get("mtime") == mtime:
                return cached["data"]
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                _yaml_cache[key] = {"mtime": mtime, "data": data}
                logger.info(f"[{label}] 加载话术模板成功，{len(data.get('scenarios', []))} 个场景")
                return data
    except Exception as e:
        logger.error(f"[{label}] 加载 YAML 失败: {e}")
    return {"principles": [], "scenarios": []}


def _load_negotiation_scripts() -> Dict[str, Any]:
    """加载价格谈判 YAML 话术模板（mtime缓存，文件修改后自动重载）"""
    return _load_yaml_with_mtime_cache(NEGOTIATION_YAML_PATH, "Negotiation")


def _build_negotiation_system_prompt() -> str:
    """
    从 YAML 构建谈判 System Prompt

    Returns:
        拼接了谈判原则和场景摘要的 System Prompt
    """
    scripts = _load_negotiation_scripts()
    principles = scripts.get("principles", [])
    scenarios = scripts.get("scenarios", [])

    parts = [
        "你是一位经验丰富的丰田汽车销售顾问，正在与客户进行价格谈判。",
        "",
        "【核心谈判原则】",
    ]
    for i, p in enumerate(principles, 1):
        parts.append(f"{i}. {p}")

    parts.append("")
    parts.append("【可选谈判场景】")
    for s in scenarios:
        sid = s.get("id", "")
        sname = s.get("name", "")
        keywords = s.get("trigger_keywords", [])
        kw_str = "、".join(keywords[:6]) if keywords else "通用"
        parts.append(f"- {sname}（{sid}），触发词：{kw_str}")

    parts.append("")
    parts.append("【回复要求】")
    parts.append("1. 根据客户消息匹配最合适的谈判场景")
    parts.append("2. 自然融入丰田品牌优势（油耗低、保值率高、故障率低、售后网点多）")
    parts.append("3. 回复简洁专业，不超过 300 字")
    parts.append("4. 语气热情但不谄媚，专业但不生硬")
    parts.append("5. 以引导到店试驾/面谈为最终目标")

    return "\n".join(parts)


def _match_scenario_by_keywords(user_message: str) -> Optional[Dict[str, Any]]:
    """
    纯关键词匹配场景（LLM 失败时的兜底）

    trigger_keywords 格式：逗号分隔的字符串，如 "便宜, 优惠, 折扣, 打折"
    匹配时按逗号拆分，逐关键词检查是否在用户消息中出现

    Args:
        user_message: 用户消息

    Returns:
        匹配到的场景字典，或 None
    """
    scripts = _load_negotiation_scripts()
    scenarios = scripts.get("scenarios", [])

    message_lower = user_message.lower()
    best_scenario = None
    max_matches = 0

    for scenario in scenarios:
        kw_raw = scenario.get("trigger_keywords", "")
        if not kw_raw or not isinstance(kw_raw, str) or not kw_raw.strip():
            continue  # 跳过通用场景（空字符串触发词）
        # 逗号分隔拆分关键词
        keywords = [kw.strip().lower() for kw in kw_raw.split(",") if kw.strip()]
        matches = sum(1 for kw in keywords if kw in message_lower)
        if matches > max_matches:
            max_matches = matches
            best_scenario = scenario

    # 如果没有匹配到具体场景，使用通用谈判场景
    if not best_scenario:
        for scenario in scenarios:
            if scenario.get("id") == "general_negotiation":
                best_scenario = scenario
                break

    return best_scenario


def _format_template(template: str, context: Dict[str, Any]) -> str:
    """
    用上下文填充模板中的占位符（{xxx} 格式）

    对缺失的占位符填入合理的默认值，确保不输出裸 {xxx}
    """
    defaults = {
        "model_name": "这款车",
        "key_feature_1": "T-Pilot 智能驾驶辅助",
        "fuel_economy": "5",
        "annual_saving": "3000",
        "resale_value": "70",
        "guide_price": "指导价",
        "tax": "约1.5万",
        "insurance": "约6000",
        "plate_fee": "500",
        "total_price": "落地价",
        "three_year_saving": "2-3",
        "competitor_name": "其他品牌",
        "our_fuel": "5.0",
        "comp_fuel": "7.0",
        "our_resale": "70",
        "comp_resale": "55",
        "our_maintenance": "800",
        "comp_maintenance": "1500",
        "comp_advantage": "智能化配置",
        "down_24": "8",
        "down_36": "6",
        "down_60": "4",
        "monthly_24": "3500",
        "monthly_36": "2500",
        "monthly_60": "1800",
        "min_down": "4",
        "min_monthly": "1800",
        "promotion_info": "0利率分期",
        "budget_range": "10-15",
        "low_trim_name": "入门版",
        "low_trim_features": "LED大灯、自动空调、倒车影像",
        "low_trim_price": "15",
        "lower_model": "卡罗拉/雷凌",
        "lower_price": "12",
        "cash_discount": "5000",
        "gift_package": "原厂脚垫+全车贴膜+行车记录仪",
        "gift_value": "3000",
        "insurance_offer": "首年交强险免费",
        "days_left": "7",
        "gift_item_1": "原厂脚垫",
        "gift_item_2": "全车3M贴膜",
        "gift_item_3": "行车记录仪",
        "gift1_value": "800",
        "gift2_value": "1500",
        "gift3_value": "500",
        "total_gift_value": "2800",
        "extra_gift": "两次免费保养",
        "group_size": "2",
    }
    # 合并用户上下文覆盖默认值
    merged = {**defaults, **context}

    def replacer(match):
        key = match.group(1)
        return str(merged.get(key, match.group(0)))

    return re.sub(r"\{(\w+)\}", replacer, template)

def _load_complaint_scripts() -> Dict[str, Any]:
    """加载投诉处理 YAML 话术模板（mtime缓存，文件修改后自动重载）"""
    return _load_yaml_with_mtime_cache(COMPLAINT_YAML_PATH, "Complaint")


def _build_complaint_system_prompt() -> str:
    """
    从 YAML 构建投诉处理 System Prompt

    Returns:
        拼接了处理原则和场景摘要的 System Prompt
    """
    scripts = _load_complaint_scripts()
    principles = scripts.get("principles", [])
    scenarios = scripts.get("scenarios", [])

    parts = [
        "你是一位经验丰富的丰田汽车售后投诉处理专家，负责安抚客户情绪并妥善解决问题。",
        "",
        "【核心投诉处理原则】",
    ]
    for i, p in enumerate(principles, 1):
        parts.append(f"{i}. {p}")

    parts.append("")
    parts.append("【可选投诉场景】")
    for s in scenarios:
        sid = s.get("id", "")
        sname = s.get("name", "")
        keywords = s.get("trigger_keywords", [])
        kw_str = "、".join(keywords[:6]) if keywords else "通用"
        parts.append(f"- {sname}（{sid}），触发词：{kw_str}")

    parts.append("")
    parts.append("【回复要求】")
    parts.append("1. 第一时间表达歉意和理解，绝不推诿或争辩")
    parts.append("2. 根据客户消息匹配最合适的投诉场景")
    parts.append("3. 给出具体可执行的解决方案和明确的时间承诺")
    parts.append("4. 语气诚恳温暖，让客户感受到被重视")
    parts.append("5. 回复不超过300字，重点突出处理方案")

    return "\n".join(parts)


def _match_complaint_scenario_by_keywords(user_message: str) -> Optional[Dict[str, Any]]:
    """
    纯关键词匹配投诉场景（LLM 失败时的兜底）

    Args:
        user_message: 用户消息

    Returns:
        匹配到的场景字典，或 None
    """
    scripts = _load_complaint_scripts()
    scenarios = scripts.get("scenarios", [])

    message_lower = user_message.lower()
    best_scenario = None
    max_matches = 0

    for scenario in scenarios:
        kw_raw = scenario.get("trigger_keywords", "")
        if not kw_raw or not isinstance(kw_raw, str) or not kw_raw.strip():
            continue  # 跳过通用场景（空字符串触发词）
        keywords = [kw.strip().lower() for kw in kw_raw.split(",") if kw.strip()]
        matches = sum(1 for kw in keywords if kw in message_lower)
        if matches > max_matches:
            max_matches = matches
            best_scenario = scenario

    # 如果没有匹配到具体场景，使用通用投诉场景
    if not best_scenario:
        for scenario in scenarios:
            if scenario.get("id") == "general_complaint":
                best_scenario = scenario
                break

    return best_scenario


COMPLAINT_SCENE_ALIASES = {
    "product_quality": "quality",
    "service_attitude": "service",
    "delivery_delay": "delivery",
    "extra_charges": "price",
    "price_dispute": "price",
    "after_sales": "after_sales",
    "general_complaint": "other",
}


# These terms cover natural phrasing that may not occur verbatim in the YAML
# keyword list (for example, “质量太差” versus “质量差”).  Keep the stable
# labels here so reporting and the regression suite do not depend on YAML IDs.
COMPLAINT_SCENE_KEYWORDS = {
    "quality": ("质量太差", "质量不好", "质量问题", "车有问题", "开了一个月就出问题", "故障", "坏了", "异响", "漏水", "漏油"),
    "service": ("服务态度", "态度太差", "态度不好", "不理人", "没人理", "冷漠", "不耐烦"),
    "delivery": ("交车", "交付", "延迟", "迟迟", "还没交车", "等车", "说好一个月"),
    "price": ("刚买完就降价", "买完降价", "降价", "价格欺骗", "价格争议", "加价", "乱收费"),
    "after_sales": ("售后", "维修", "保养", "修不好", "维修排队", "排队排了很久", "返修"),
}


def classify_complaint_scene(user_message: str) -> str:
    """Classify a complaint into a stable scene name used by tests and analytics."""
    message = user_message or ""
    for scene, keywords in COMPLAINT_SCENE_KEYWORDS.items():
        if any(keyword in message for keyword in keywords):
            return scene
    scenario = _match_complaint_scenario_by_keywords(user_message)
    scenario_id = scenario.get("id", "general_complaint") if scenario else "general_complaint"
    return COMPLAINT_SCENE_ALIASES.get(scenario_id, "other")


def is_complaint_reply_compliant(reply: str) -> bool:
    """Require apology, empathy, solution and follow-up commitment in complaint replies."""
    text = reply or ""
    required_groups = [
        ("抱歉", "歉意", "对不起"),
        ("理解", "心情", "体验", "重视"),
        ("解决", "处理", "检查", "安排", "方案"),
        ("跟进", "联系", "回复", "回访", "承诺"),
    ]
    return all(any(keyword in text for keyword in group) for group in required_groups)


def ensure_complaint_reply_compliant(reply: str) -> str:
    """Add an explicit ownership/follow-up promise to a YAML fallback if needed."""
    if is_complaint_reply_compliant(reply):
        return reply

    suffix = "\n\n我会持续跟进此事，并在2小时内主动联系您反馈处理进度。"
    return f"{reply.rstrip()}{suffix}"


SALES_RESPONSE_PROMPT = """你是一位专业的丰田汽车销售顾问，精通广汽丰田、一汽丰田、进口丰田全系车型。

【回复原则】
1. 先说结论，回复要简短专业
2. 基于知识库数据准确回答，不编造
3. 分点清晰方便阅读
4. 自然收尾，问问客户还有其他需求吗

【重要能力说明】
- 你可以发送车型图片。当客户询问车型或要求看图时，系统会在文字回复下方自动展示对应图片。
- 你只需要正常介绍车型，不需要手动生成链接或解释图片发送过程。
- 绝对不要说“无法发送图片”“暂不支持图片”或“无法直接发送”。

【严禁】
- ❌ 不使用重复多余的修辞
- ❌ 不超过300字（报价单生成回复除外）
- ❌ 不要在回复中包含任何下载链接或文件路径（前端有下载按钮，不需要重复）
- ❌ 当生成了报价单/方案书后，只需说"这是您的报价单，点击下方按钮即可下载"，不要贴链接

【预约服务特殊规则】
- 当客户想预约线下服务，先问清楚要预约什么：购车还是售后
- 购车：询问想看的车型、预算、方便的时间
- 售后：询问车型、车牌号、具体问题（保养/检修/维修）

请生成简洁专业的回复。"""


def _get_default_reply(intent: UserIntent = None) -> str:
    """获取默认回复（兜底）"""
    intent_replies = {
        UserIntent.QUOTE_GENERATION: "这是您的报价单，点击下方按钮即可下载。",
        UserIntent.DOCUMENT_REQUEST: "已为您生成文档，点击下载即可查看。",
        UserIntent.PROPOSAL_CREATION: "方案已生成，如需调整请告诉我。",
        UserIntent.CONTRACT_DRAFTING: "合同草案已准备就绪，请审阅。",
        UserIntent.PRODUCT_INQUIRY: "您好，我是丰田汽车顾问，专注广汽丰田/一汽丰田/进口丰田全系。想了解哪款车的配置和价格？",
        UserIntent.PRICE_NEGOTIATION: "已收到您的询价需求，正在为您查询最优价格方案。",
        UserIntent.COMPLAINT_HANDLING: "抱歉给您带来不好的体验，我马上为您处理。",
        UserIntent.FOLLOW_UP: "好的，有进展我会通知您。",
        UserIntent.ANALYZE_CAR_IMAGE: "我来分析一下这张图片。",
        UserIntent.GENERATE_CUSTOM_CAR: "效果图正在生成中，完成后发给您。",
        UserIntent.SERVICE_APPOINTMENT: "您好！请问您想预约什么服务呢？\n\n1️⃣ 线下购车——到店看车、试驾、谈价格\n2️⃣ 售后服务——保养、检修、维修等\n\n请告诉我您的需求，我帮您安排～",
    }
    
    if intent and intent in intent_replies:
        return intent_replies[intent]
    
    return "您好！我是丰田汽车顾问，专注广汽丰田/一汽丰田/进口丰田全系。想了解哪款车的配置和价格？"


async def sales_response_node(state: SalesState) -> SalesState:
    """
    销售回复节点 - 生成汽车销售回复（多模态汽车金牌销售顾问版）
    
    防御性设计：
    - 如果已有 sales_response，直接返回
    - 如果没有，使用 LLM 生成
    - LLM 失败时使用兜底回复
    """
    session_id = state.get("session_id", "unknown")
    logger.info(f"[Session: {session_id}] 生成销售回复")
    
    # 如果已有回复，直接返回（可能由前面节点生成）
    existing_reply = state.get("sales_response")
    if existing_reply and isinstance(existing_reply, str) and len(existing_reply.strip()) > 0:
        logger.debug("[Response] 使用已有回复")
        state["next_node"] = "end"
        return state
    
    # 获取意图信息
    intent_analysis = state.get("intent_analysis")
    intent = UserIntent.GENERAL_CHAT
    if intent_analysis and hasattr(intent_analysis, 'intent'):
        intent = intent_analysis.intent
    
    try:
        # 准备上下文
        knowledge_response = state.get("metadata", {}).get("knowledge_response", "")
        generated_docs = state.get("generated_documents", [])
        generated_media = state.get("generated_media", [])
        
        context_parts = []
        
        if knowledge_response:
            context_parts.append(f"[车型知识信息]\n{knowledge_response}")
        
        if generated_docs and len(generated_docs) > 0:
            doc_names = []
            for doc in generated_docs:
                if isinstance(doc, dict):
                    doc_names.append(doc.get("file_name", "文档"))
                elif hasattr(doc, 'file_name'):
                    doc_names.append(doc.file_name)
            if doc_names:
                context_parts.append(f"[已生成文档]\n{', '.join(doc_names)}")
        
        if generated_media and len(generated_media) > 0:
            context_parts.append(f"[已生成媒体]\n为您定制了 {len(generated_media)} 张效果图/视频")
        
        context_str = "\n\n".join(context_parts) if context_parts else "无额外上下文"
        
        messages = state.get("messages", [])
        user_message = ""
        # 提取最近 N 条对话历史，让 LLM 理解上下文
        recent_history = []
        if messages and len(messages) > 0:
            for m in messages[-MAX_CONTEXT_MESSAGES:]:
                role = "用户"
                if hasattr(m, 'type'):
                    role = "用户" if m.type == 'human' else "助手"
                elif isinstance(m, dict):
                    role = "用户" if m.get('role') == 'user' else "助手"
                content = getattr(m, 'content', str(m)) if not isinstance(m, dict) else m.get('content', '')
                recent_history.append(f"{role}: {content}")
            # 最后一条是当前用户消息
            last_msg = messages[-1]
            if hasattr(last_msg, 'content'):
                user_message = last_msg.content
            elif isinstance(last_msg, dict):
                user_message = last_msg.get("content", "")
        
        history_str = "\n".join(recent_history[:-1]) if len(recent_history) > 1 else "无历史"
        
        llm = ChatOpenAI(
            model=settings.default_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.7,
        )
        
        prompt = f"""{SALES_RESPONSE_PROMPT}

【对话历史（用于理解上下文，回复要衔接自然）】
{history_str}

【当前用户消息】
{user_message}

【识别意图】{intent.value if hasattr(intent, 'value') else str(intent)}

【上下文信息】
{context_str}

请基于对话历史理解上下文，生成简洁、专业、连贯的销售回复："""

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content="请生成回复")
        ])
        
        reply = response.content if hasattr(response, 'content') else str(response)
        
        # 当有生成文档时，移除LLM回复中的URL（前端按钮已处理下载）
        if generated_docs and len(generated_docs) > 0:
            import re as _re
            reply = _re.sub(r'https?://\S+', '', reply)
            reply = _re.sub(r'下载链接[：:]\s*\n?', '', reply)
            reply = _re.sub(r'可直接在浏览器打开下载[，,。.]?', '', reply)
            reply = _re.sub(r'\n{3,}', '\n\n', reply).strip()
        
        suggested_actions_map = {
            UserIntent.PRODUCT_INQUIRY: ["获取报价", "了解详情"],
            UserIntent.PRICE_NEGOTIATION: ["申请优惠", "进一步咨询"],
            UserIntent.QUOTE_GENERATION: ["调整需求", "下载报价"],
            UserIntent.ANALYZE_CAR_IMAGE: ["查看更多图片", "了解详情"],
            UserIntent.GENERATE_CUSTOM_CAR: ["生成更多", "了解详情"],
        }
        
        if intent in suggested_actions_map:
            suggested_actions = suggested_actions_map[intent]
        elif generated_docs and len(generated_docs) > 0:
            suggested_actions = ["下载文档", "继续咨询"]
        else:
            suggested_actions = ["继续咨询", "了解车型", "获取报价"]
        
        state["sales_response"] = reply
        state["suggested_actions"] = suggested_actions
        
        logger.info(f"[Response] 回复生成完成，长度: {len(reply)}")
        
    except Exception as e:
        logger.error(f"[Response] 生成回复失败: {e}")
        state["sales_response"] = _get_default_reply(intent)
        state["suggested_actions"] = ["继续咨询", "了解产品信息"]
    
    state["next_node"] = "end"
    return state


async def sales_negotiation_node(state: SalesState) -> SalesState:
    """
    价格谈判节点 - YAML 话术模板 + LLM 场景匹配版

    流程：
    1. 加载 YAML 谈判话术模板
    2. 用 LLM 匹配场景并生成个性化回复
    3. LLM 失败 → YAML 关键词匹配兜底
    4. YAML 失败 → 硬编码默认回复兜底

    防御性设计：绝不抛异常，始终返回有效回复
    """
    session_id = state.get("session_id", "unknown")
    logger.info(f"[Session: {session_id}] 处理价格谈判")

    # 如果前面的节点已经生成了回复，直接返回
    existing_reply = state.get("sales_response")
    if existing_reply and isinstance(existing_reply, str) and len(existing_reply.strip()) > 0:
        state["next_node"] = "end"
        return state

    # 获取用户消息
    user_message = ""
    try:
        messages = state.get("messages", [])
        if messages and isinstance(messages, list):
            last_msg = messages[-1]
            if hasattr(last_msg, "content"):
                user_message = last_msg.content or ""
            elif isinstance(last_msg, dict):
                user_message = last_msg.get("content", "")
    except Exception:
        user_message = ""

    # 获取上下文中的车型信息
    context = state.get("context", {}) or {}

    # ═══ 第一层：LLM 生成个性化谈判回复 ═══
    try:
        llm = ChatOpenAI(
            model=settings.default_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.7,
        )

        system_prompt = _build_negotiation_system_prompt()

        user_prompt = f"""客户消息：{user_message}

上下文信息：
- 客户关注车型：{context.get('car_model', '未指定')}
- 预算范围：{context.get('budget_range', '未提及')}
- 客户名称：{context.get('customer_name', '未提及')}

请以丰田销售顾问身份，生成一段自然、有说服力的价格谈判回复："""

        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        reply = response.content if hasattr(response, "content") else str(response)

        if reply and len(reply.strip()) > 10:
            state["sales_response"] = reply.strip()
            state["suggested_actions"] = ["预约到店详谈", "申请优惠", "了解金融方案"]
            state["next_node"] = "end"
            logger.info(f"[Negotiation] LLM 回复生成完成，长度: {len(reply)}")
            return state

    except Exception as e:
        logger.warning(f"[Negotiation] LLM 调用失败，回退到 YAML 模板: {e}")

    # ═══ 第二层：YAML 关键词匹配兜底 ═══
    try:
        scenario = _match_scenario_by_keywords(user_message)
        if scenario:
            strategies = scenario.get("response_strategies", [])
            if strategies:
                template = strategies[0].get("template", "")
                if template:
                    reply = _format_template(template, context)
                    state["sales_response"] = reply
                    state["suggested_actions"] = scenario.get("suggested_actions", ["预约到店详谈", "了解更多优惠"])
                    state["next_node"] = "end"
                    logger.info(f"[Negotiation] YAML 模板匹配: {scenario.get('name', 'unknown')}")
                    return state
    except Exception as e:
        logger.warning(f"[Negotiation] YAML 模板匹配失败: {e}")

    # ═══ 第三层：硬编码最终兜底 ═══
    state["sales_response"] = (
        "感谢您的关注！关于价格方面，我们可以在以下几个方面帮您：\n\n"
        "💰 **省钱攻略**\n"
        "1️⃣ 现金优惠 — 根据车型和库存有不同优惠\n"
        "2️⃣ 金融分期 — 低首付低月供，灵活选择\n"
        "3️⃣ 置换补贴 — 旧车置换享额外补贴\n"
        "4️⃣ 精品礼包 — 购车即送原厂精品\n\n"
        "具体优惠需要到店详谈，我帮您争取最大空间。您方便哪天来店里？"
    )
    state["suggested_actions"] = ["预约到店详谈", "了解金融方案", "获取报价"]
    state["next_node"] = "end"
    logger.info("[Negotiation] 使用硬编码默认回复")
    return state


async def complaint_handler_node(state: SalesState) -> SalesState:
    """
    投诉处理节点 - YAML 话术模板 + LLM 场景匹配版

    流程：
    1. 加载 YAML 投诉处理话术模板
    2. 用 LLM 匹配场景并生成个性化回复
    3. LLM 失败 → YAML 关键词匹配兜底
    4. YAML 失败 → 硬编码默认回复兜底

    防御性设计：绝不抛异常，始终返回有效回复
    """
    session_id = state.get("session_id", "unknown")
    logger.info(f"[Session: {session_id}] 处理客户投诉")

    # 如果前面的节点已经生成了回复，直接返回
    existing_reply = state.get("sales_response")
    if existing_reply and isinstance(existing_reply, str) and len(existing_reply.strip()) > 0:
        state["next_node"] = "end"
        return state

    # 获取用户消息
    user_message = ""
    try:
        messages = state.get("messages", [])
        if messages and isinstance(messages, list):
            last_msg = messages[-1]
            if hasattr(last_msg, "content"):
                user_message = last_msg.content or ""
            elif isinstance(last_msg, dict):
                user_message = last_msg.get("content", "")
    except Exception:
        user_message = ""

    # 获取上下文
    context = state.get("context", {}) or {}
    scene = classify_complaint_scene(user_message)
    scenario = _match_complaint_scenario_by_keywords(user_message)
    # Prefer the deterministic scene mapping when natural wording was not an
    # exact YAML keyword match, so the corresponding YAML remedy is used.
    if not scenario or COMPLAINT_SCENE_ALIASES.get(scenario.get("id"), "other") != scene:
        scenario = next(
            (
                item for item in _load_complaint_scripts().get("scenarios", [])
                if COMPLAINT_SCENE_ALIASES.get(item.get("id"), "other") == scene
            ),
            scenario,
        )
    state["metadata"] = state.get("metadata", {})
    state["metadata"]["complaint_scene"] = scene
    logger.info("[Complaint] 场景分类: %s", scene)

    # ═══ 第一层：LLM 生成个性化投诉处理回复 ═══
    try:
        llm = ChatOpenAI(
            model=settings.default_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.7,
        )

        system_prompt = _build_complaint_system_prompt()

        user_prompt = f"""客户投诉消息：{user_message}

上下文信息：
- 客户名称：{context.get('customer_name', '未提及')}
- 投诉时间：{context.get('complaint_time', '当前')}
- 涉及车型：{context.get('car_model', '未提及')}

请以丰田售后投诉处理专家身份，生成一段诚恳、专业的投诉处理回复："""

        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        reply = response.content if hasattr(response, "content") else str(response)

        if reply and len(reply.strip()) > 10 and is_complaint_reply_compliant(reply):
            state["sales_response"] = reply.strip()
            state["suggested_actions"] = ["预约售后检测", "投诉升级处理", "转接售后经理"]
            state["next_node"] = "end"
            logger.info(f"[Complaint] LLM 回复生成完成，长度: {len(reply)}")
            return state
        logger.warning("[Complaint] LLM 回复缺少投诉处理闭环，回退到 YAML 模板")

    except Exception as e:
        logger.warning(f"[Complaint] LLM 调用失败，回退到 YAML 模板: {e}")

    # ═══ 第二层：YAML 关键词匹配兜底 ═══
    try:
        if scenario:
            strategies = scenario.get("response_strategies", [])
            if strategies:
                template = strategies[0].get("template", "")
                if template:
                    reply = ensure_complaint_reply_compliant(_format_template(template, context))
                    state["sales_response"] = reply
                    state["suggested_actions"] = scenario.get("suggested_actions", ["反馈详细信息", "转接人工客服"])
                    state["next_node"] = "end"
                    logger.info(f"[Complaint] YAML 模板匹配: {scenario.get('name', 'unknown')}")
                    return state
    except Exception as e:
        logger.warning(f"[Complaint] YAML 模板匹配失败: {e}")

    # ═══ 第三层：硬编码最终兜底 ═══
    state["sales_response"] = (
        "非常抱歉给您带来了不好的体验！\n\n"
        "我会立即记录您的问题：\n"
        "1. 记录问题详情并反馈给相关部门\n"
        "2. 2小时内安排专人与您联系\n"
        "3. 全程跟进直到问题妥善解决\n\n"
        "请问方便留个电话吗？方便我们及时联系您。\n"
        "再次为给您造成的不便深表歉意，一定给您一个满意的答复。"
    )
    state["suggested_actions"] = ["反馈详细信息", "转接人工客服", "留下联系方式"]
    state["next_node"] = "end"
    logger.info("[Complaint] 使用硬编码默认回复")
    return state


# 兼容性导出
clarify_document_type_node = sales_response_node
