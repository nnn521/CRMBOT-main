"""
多模态处理节点 - 视觉识别与媒体生成（微信式双气泡版）

【生产就绪版】真实智谱 API 集成 + 微信式交互
- vision_analysis_node: 汽车图片视觉分析（调用 GLM-4V）
- media_generation_node: 定制汽车图片生成（调用 CogView-3）

【微信式双气泡核心设计】
1. 图片消息：使用 HTML <img> 标签，独立气泡
2. 文字消息：纯文字销售话术，独立气泡
3. 一次性返回两条 AIMessage，前端分两个气泡渲染
"""

import asyncio
from typing import Dict, Any, Optional

from langchain_core.messages import AIMessage
from zhipuai import ZhipuAI

from app.core.config import settings
from app.core.logging import get_logger
from app.agents.state import SalesState

logger = get_logger("multimodal_node")


# ═══════════════════════════════════════════════════════════════
# 【视觉分析节点】vision_analysis_node - 汽车的"眼睛"
# ═══════════════════════════════════════════════════════════════

VISION_ANALYSIS_PROMPT = """你是一位资深汽车鉴定专家，擅长通过图片识别汽车的各种特征。

请仔细分析用户上传的汽车图片，识别以下信息：
1. **品牌**：保时捷、比亚迪、奔驰、宝马、奥迪等
2. **车型**：具体型号（如 911 Carrera、Panamera、汉EV、海豹等）
3. **颜色**：车漆颜色（如冰莓粉、午夜蓝、火山灰、液态银等）
4. **外观亮点**：运动套件、轮毂样式、卡钳颜色、尾翼、车灯设计等
5. **整体状态**：新车/二手车、改装程度、保养状况

输出格式要求（简洁专业，适合销售顾问参考）：
- 用一句话概括车型识别结果
- 列出 2-3 个最突出的外观亮点
- 给出针对性的销售话术建议

示例输出：
识别到保时捷Panamera行政加长版，火山灰金属漆，配有21英寸Exclusive Design轮毂和红色制动卡钳。建议突出其商务与运动兼顾的定位。"""


async def vision_analysis_node(state: SalesState) -> Dict[str, Any]:
    """
    视觉分析节点 - 分析用户上传的汽车图片

    输出（经 ainvoke 与 checkpoint 合并）：
    - sales_response: 视觉分析 + 销售话术文本（chat API 直接返回给客户）
    - messages: 追加一条 AIMessage，让 checkpoint 记忆包含本次回复
    - context: 记录分析结果
    """
    session_id = state.get("session_id", "unknown")
    logger.info(f"[Session: {session_id}] 开始视觉分析节点")

    # 提取图片 URL
    input_image_url = state.get("input_image_url")

    if not input_image_url:
        # 没有图片时给出引导文案，而不是静默返回空更新
        guidance = (
            "想让我帮您分析汽车图片的话，请把图片链接发给我（或上传图片）。\n\n"
            "我可以通过外观识别品牌、车型、颜色和亮点配置，并给出专业的销售建议～"
        )
        state["sales_response"] = guidance
        state["suggested_actions"] = ["发送图片链接", "文字描述车型"]
        state["next_node"] = "end"
        return {
            "sales_response": guidance,
            "suggested_actions": ["发送图片链接", "文字描述车型"],
            "messages": [AIMessage(content=guidance)],
            "next_node": "end",
        }

    logger.info(f"[Vision] 检测到图片 URL: {input_image_url}")

    context = state.get("context", {})
    if not isinstance(context, dict):
        context = {}

    # 调用 GLM-4V 分析
    try:
        analysis_result = await _call_glm4v_vision_api(image_url=input_image_url)
        logger.info(f"[Vision] 视觉分析完成: {analysis_result[:100]}...")
    except Exception as e:
        logger.error(f"[Vision] 视觉分析 API 调用失败: {e}")
        analysis_result = _get_fallback_vision_analysis(input_image_url)

    # 更新 context
    vision_context = {
        "vision_analysis": analysis_result,
        "input_image_url": input_image_url,
    }
    updated_context = {**context, **vision_context}

    # 销售话术正文（修复：写入 sales_response，chat API 才能返回给客户）
    analysis_text = (
        f"📸 **我看到您分享的汽车图片了！**\n\n"
        f"{analysis_result}\n\n"
        f"🏎️ 作为一名资深汽车顾问，我对这款车型非常熟悉！\n"
        f"如果您想看到更多角度的效果图，或者想了解详细配置和报价，随时告诉我！"
    )

    msg_analysis = AIMessage(content=analysis_text)

    logger.info(f"[Vision] 视觉分析节点完成")

    return {
        "messages": [msg_analysis],
        "sales_response": analysis_text,
        "suggested_actions": ["查看更多图片", "了解详情", "获取报价"],
        "context": updated_context,
        "next_node": "end",
    }


async def _call_glm4v_vision_api(image_url: str) -> str:
    """【真实 API】调用智谱 GLM-4V 视觉大模型"""
    logger.info(f"[GLM-4V] 调用视觉分析 API - Image: {image_url[:60]}...")
    
    if not settings.zhipu_api_key:
        logger.warning("[GLM-4V] zhipu_api_key 为空，无法调用智谱视觉API，将使用兜底分析")
        raise ValueError("zhipu_api_key is not configured")
    
    try:
        client = ZhipuAI(api_key=settings.zhipu_api_key)

        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="glm-4v",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_ANALYSIS_PROMPT},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                temperature=0.3,
                max_tokens=500
            )
        )
        
        analysis = response.choices[0].message.content
        logger.info(f"[GLM-4V] 视觉分析成功，返回 {len(analysis)} 字符")
        return f"【AI视觉分析结果】\n{analysis}"
        
    except Exception as e:
        logger.error(f"[GLM-4V] API 调用失败: {e}")
        raise


def _get_fallback_vision_analysis(image_url: str) -> str:
    """视觉分析兜底函数"""
    return (
        "【系统提示：图片已接收】\n"
        "用户上传了一张汽车图片，由于网络原因暂时无法详细分析车型。"
        "建议销售顾问询问客户具体车型和感兴趣的配置，并提供专业建议。"
    )


# ═══════════════════════════════════════════════════════════════
# 【媒体生成节点】media_generation_node - 销售的"神笔"
# ═══════════════════════════════════════════════════════════════

async def media_generation_node(state: SalesState) -> Dict[str, Any]:
    """
    媒体生成节点 - 生成定制汽车图片

    输出（经 ainvoke 与 checkpoint 合并）：
    - sales_response: 销售话术正文（chat API 直接返回给客户）
    - images: 生成的效果图 URL（前端图片网格 + 灯箱展示，不再依赖 HTML）
    - messages: 追加一条 AIMessage 记忆
    """
    session_id = state.get("session_id", "unknown")
    logger.info(f"[Session: {session_id}] 开始媒体生成节点")

    # 提取用户需求
    messages = state.get("messages", [])
    user_message = ""
    if messages and len(messages) > 0:
        last_msg = messages[-1]
        if hasattr(last_msg, 'content'):
            user_message = last_msg.content
        elif isinstance(last_msg, dict):
            user_message = last_msg.get("content", "")

    context = state.get("context", {})
    car_model = context.get("car_model", "")
    color_preference = context.get("color_preference", "")

    logger.info(f"[Media] 用户需求: {user_message[:50]}...")
    logger.info(f"[Media] 车型: {car_model or '未指定'}, 颜色: {color_preference or '未指定'}")

    # 构建生成提示词
    if user_message and len(user_message) > 5:
        prompt = _build_image_prompt_from_message(user_message, car_model, color_preference)
    else:
        model_str = car_model if car_model else "豪华跑车"
        color_str = color_preference if color_preference else "优雅配色"
        prompt = f"一辆{model_str}，{color_str}，专业汽车摄影，展厅灯光，高清细节，商业广告级别，8K超高清"

    logger.info(f"[Media] 图片生成提示词: {prompt[:80]}...")

    # 调用 CogView-3 生成图片
    generated_image_url = None
    try:
        generated_image_url = await _call_cogview3_image_api(prompt)
        logger.info(f"[Media] 图片生成成功: {generated_image_url[:60]}...")
    except Exception as e:
        logger.error(f"[Media] 图片生成失败: {e}")

    car_name = car_model if car_model else "您的专属座驾"

    if generated_image_url:
        sales_text = f"""✨ **这是为您精心定制的 {car_name} 效果图！**

🏎️ 这效果简直令人惊艳！从流线型车身到精致的细节处理，每一处都彰显着顶级工艺。

💡 **温馨提示**：
- 效果图由 AI 根据您的描述生成，仅供参考
- 实际颜色和细节可能因光线、角度略有差异
- 强烈建议您**预约到店看实车**，感受真正的车漆质感和驾驶体验！

🎯 如果您对这个效果满意，我可以立即为您安排试驾、获取报价，或了解更多定制配置选项！

还有什么想调整的吗？我可以为您生成更多角度或配色方案！"""
        suggested = ["生成更多配色", "预约试驾", "获取报价"]
    else:
        sales_text = (
            f"抱歉，定制 {car_name} 效果图的生成服务暂时不可用（未配置图片生成接口或调用失败）。\n\n"
            "您可以直接告诉我车型和配色偏好，我仍然可以为您介绍配置、报价并预约到店看实车～"
        )
        suggested = ["文字介绍配置", "获取报价", "预约试驾"]

    msg_text = AIMessage(content=sales_text)

    # 更新 generated_media 列表
    existing_media = state.get("generated_media", [])
    if not isinstance(existing_media, list):
        existing_media = []
    updated_media = existing_media + ([generated_image_url] if generated_image_url else [])

    # 更新 context
    updated_context = {
        **context,
        "last_generated_prompt": prompt,
        "last_generated_image": generated_image_url,
    }

    logger.info(f"[Media] 媒体生成节点完成")

    return {
        "messages": [msg_text],
        "sales_response": sales_text,
        "suggested_actions": suggested,
        "images": [generated_image_url] if generated_image_url else [],
        "generated_media": updated_media,
        "context": updated_context,
        "next_node": "end",
    }


async def _call_cogview3_image_api(prompt: str) -> str:
    """【真实 API】调用智谱 CogView-3 生成图片"""
    logger.info(f"[CogView-3] 生成图片 - Prompt: {prompt[:60]}...")
    
    if not settings.zhipu_api_key:
        logger.warning("[CogView-3] zhipu_api_key 为空，无法调用智谱图片生成API")
        raise ValueError("zhipu_api_key is not configured")
    
    try:
        client = ZhipuAI(api_key=settings.zhipu_api_key)

        response = await asyncio.to_thread(
            lambda: client.images.generations(
                model="cogview-3-plus",
                prompt=prompt,
                size="1024x768"
            )
        )
        
        image_url = response.data[0].url
        logger.info(f"[CogView-3] 图片生成成功: {image_url[:60]}...")
        return image_url
        
    except Exception as e:
        logger.error(f"[CogView-3] API 调用失败: {e}")
        raise


def _build_image_prompt_from_message(
    user_message: str, 
    car_model: str = "", 
    color: str = ""
) -> str:
    """从用户消息构建图片生成提示词"""
    message_lower = user_message.lower()
    
    # 确定车型
    model = car_model
    if not model:
        if "911" in user_message:
            model = "保时捷911"
        elif "panamera" in message_lower:
            model = "保时捷Panamera"
        elif "taycan" in message_lower:
            model = "保时捷Taycan"
        elif "汉" in user_message:
            model = "比亚迪汉EV"
        elif "海豹" in user_message:
            model = "比亚迪海豹"
        else:
            model = "豪华跑车"
    
    # 确定颜色
    car_color = color
    if not car_color:
        color_keywords = {
            "冰莓粉": "冰莓粉", "粉色": "冰莓粉", "粉": "冰莓粉",
            "午夜蓝": "午夜蓝", "深蓝": "午夜蓝", "蓝色": "蓝色",
            "火山灰": "火山灰", "灰色": "灰色", "银": "GT银",
            "白色": "白色", "黑色": "黑色", "红色": "红色",
            "绿色": "墨绿色", "黄色": "竞速黄", "橙色": "熔岩橙"
        }
        for kw, color_name in color_keywords.items():
            if kw in user_message:
                car_color = color_name
                break
    
    if not car_color:
        car_color = "优雅配色"
    
    # 构建最终提示词
    prompt = f"一辆{model}，{car_color}车漆，专业汽车摄影，展厅灯光，高清细节，侧面45度角，白色背景，商业广告级别，8K超高清"
    
    return prompt


# 兼容性导出
analyze_car_image_node = vision_analysis_node
generate_custom_car_node = media_generation_node
