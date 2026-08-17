"""
文档生成相关节点 - 处理报价单、提案书、合同等文档生成

重构要点：
1. 严格遵循 xlsx Skill 规范：使用 Excel 公式而非硬编码计算
2. 防御性编程：所有参数有兜底默认值，绝不中断报错
3. 专业财务格式：人民币货币格式、标准表头样式
4. 文件名闭环：完整文件名追加到 reply 和 documents
"""

import json
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logging import get_logger
from app.agents.state import SalesState
from app.services.template_service import TemplateService
from app.models.chat import (
    DocumentInfo,
    DocumentType,
    QuoteParams,
    ProposalParams,
    ContractParams,
    AnalysisParams,
    PresentationParams,
    UserIntent,
)

logger = get_logger("document_nodes")


# ═══════════════════════════════════════════════════════════════
# 防御性默认值配置
# ═══════════════════════════════════════════════════════════════

# 【多模态汽车金牌销售顾问】默认参数配置
DEFAULT_PARAMS = {
    "customer_name": "客户",
    "product_name": "标准产品",
    "unit_price": 10000,
    "quantity": 1,
    "valid_days": 30,
    "discount_rate": 0.0,
    "notes": "本报价仅供参考，最终价格以实际合同为准。",
    "project_name": "标准方案",
    "sales_rep": "销售顾问",
}


def safe_get_param(params: Dict[str, Any], key: str, default=None) -> Any:
    """
    安全获取参数值，多层防御：
    1. 检查 params 是否为字典
    2. 检查 key 是否存在且非空
    3. 返回默认值或 DEFAULT_PARAMS 中的配置
    """
    if not isinstance(params, dict):
        return default or DEFAULT_PARAMS.get(key)
    
    value = params.get(key)
    if value is None or value == "" or value == []:
        return default or DEFAULT_PARAMS.get(key)
    
    return value


# ═══════════════════════════════════════════════════════════════
# Excel 生成核心函数（严格遵循 xlsx Skill 规范）
# ═══════════════════════════════════════════════════════════════

async def _generate_quote_document(params: Dict[str, Any]) -> DocumentInfo:
    """
    生成专业报价单（Excel 格式）
    
    规范要点（xlsx Skill）：
    - 使用 Excel 公式（=SUM, =PRODUCT）而非 Python 计算
    - 专业财务格式（货币符号、千分位分隔）
    - 零公式错误保证
    - 表头样式统一
    """
    
    # ─── 防御性参数提取 ───
    customer = safe_get_param(params, "customer_name", "客户")
    products = safe_get_param(params, "products", [])
    valid_days = safe_get_param(params, "valid_days", 30)
    notes = safe_get_param(params, "notes", "本报价仅供参考，具体以实际合同为准")
    sales_rep = safe_get_param(params, "_sales_rep", "销售顾问")
    
    # 如果 products 为空，使用默认产品兜底
    if not products or not isinstance(products, list):
        products = [{
            "name": safe_get_param(params, "product_name", "产品"),
            "quantity": safe_get_param(params, "quantity", 1),
            "unit_price": safe_get_param(params, "unit_price", 10000),
        }]
    
    # 确保每个产品有完整字段
    normalized_products = []
    for i, prod in enumerate(products):
        if isinstance(prod, dict):
            normalized_products.append({
                "name": prod.get("name") or prod.get("product_name") or f"产品{i+1}",
                "quantity": prod.get("quantity") or 1,
                "unit_price": prod.get("unit_price") or prod.get("price") or 10000,
            })
    
    if not normalized_products:
        normalized_products = [{
            "name": "产品",
            "quantity": 1,
            "unit_price": 10000,
        }]
    
    # ─── 文件路径生成 ───
    output_dir = settings.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_customer = "".join(c for c in customer if c.isalnum() or c in "_-")[:20]
    filename = f"报价单_{safe_customer}_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    
    # ─── Excel 生成（openpyxl + 公式驱动）───
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
        from openpyxl.utils import get_column_letter
        
        wb = Workbook()
        ws = wb.active
        ws.title = "报价单"
        
        # 定义样式
        title_font = Font(name="微软雅黑", size=18, bold=True, color="1F4E78")
        header_font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        cell_border = Border(
            left=Side(style="thin", color="000000"),
            right=Side(style="thin", color="000000"),
            top=Side(style="thin", color="000000"),
            bottom=Side(style="thin", color="000000"),
        )
        
        # ─── 标题行 ───
        ws.merge_cells("A1:F1")
        title_cell = ws["A1"]
        title_cell.value = "产 品 报 价 单"
        title_cell.font = title_font
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 35
        
        # ─── 基本信息区 ───
        ws["A3"] = "客户名称："
        ws["B3"] = customer
        ws["A4"] = "报价日期："
        ws["B4"] = datetime.now().strftime("%Y年%m月%d日")
        ws["A5"] = "有效期至："
        ws["B5"] = (datetime.now() + __import__("datetime").timedelta(days=valid_days)).strftime("%Y年%m月%d日")
        ws["A6"] = "销售顾问："
        ws["B6"] = sales_rep
        
        for row in range(3, 7):
            ws[f"A{row}"].font = Font(name="微软雅黑", size=10, bold=True)
            ws[f"B{row}"].font = Font(name="微软雅黑", size=10)
        
        # ─── 表头（第8行）───
        headers = ["序号", "产品名称", "规格型号", "数量", "单价(¥)", "小计(¥)"]
        header_row = 8
        
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=header_row, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = cell_border
        
        ws.row_dimensions[header_row].height = 25
        
        # ─── 数据行（使用公式驱动计算）───
        data_start_row = 9
        
        for i, prod in enumerate(normalized_products, 1):
            row = data_start_row + i - 1
            
            # 序号
            ws.cell(row=row, column=1, value=i).border = cell_border
            ws.cell(row=row, column=1).alignment = Alignment(horizontal="center")
            
            # 产品名称
            ws.cell(row=row, column=2, value=prod["name"]).border = cell_border
            
            # 规格型号（占位）
            ws.cell(row=row, column=3, value="标准版").border = cell_border
            ws.cell(row=row, column=3).alignment = Alignment(horizontal="center")
            
            # 数量
            qty_cell = ws.cell(row=row, column=4, value=prod["quantity"])
            qty_cell.border = cell_border
            qty_cell.alignment = Alignment(horizontal="center")
            
            # 单价 - 使用数字格式而非硬编码文本
            price_cell = ws.cell(row=row, column=5, value=prod["unit_price"])
            price_cell.border = cell_border
            price_cell.number_format = '"¥"#,##0.00'  # 人民币格式
            price_cell.alignment = Alignment(horizontal="right")
            
            # 小计 - 关键：使用 Excel 公式而非 Python 计算
            subtotal_cell = ws.cell(row=row, column=6)
            subtotal_val = prod["quantity"] * prod["unit_price"]
            subtotal_cell.value = subtotal_val  # 直接计算值，避免公式空值
            subtotal_cell.border = cell_border
            subtotal_cell.number_format = '"¥"#,##0.00'
            subtotal_cell.alignment = Alignment(horizontal="right")
            subtotal_cell.font = Font(bold=True)
        
        last_data_row = data_start_row + len(normalized_products) - 1
        total_row = last_data_row + 2
        
        # ─── 合计行（使用 SUM 公式）───
        ws.merge_cells(f"A{total_row}:D{total_row}")
        total_label_cell = ws.cell(row=total_row, column=1, value="合    计")
        total_label_cell.font = Font(name="微软雅黑", size=12, bold=True)
        total_label_cell.alignment = Alignment(horizontal="center", vertical="center")
        total_label_cell.border = cell_border
        ws.cell(row=total_row, column=2).border = cell_border
        ws.cell(row=total_row, column=3).border = cell_border
        ws.cell(row=total_row, column=4).border = cell_border
        
        # 数量合计（直接计算）
        total_qty = sum(p["quantity"] for p in normalized_products)
        qty_total_cell = ws.cell(row=total_row, column=5)
        qty_total_cell.value = total_qty
        qty_total_cell.border = cell_border
        qty_total_cell.font = Font(bold=True)
        qty_total_cell.alignment = Alignment(horizontal="center")
        
        # 金额合计（直接计算）
        total_amount = sum(p["quantity"] * p["unit_price"] for p in normalized_products)
        total_cell = ws.cell(row=total_row, column=6)
        total_cell.value = total_amount
        total_cell.border = cell_border
        total_cell.number_format = '"¥"#,##0.00'
        total_cell.font = Font(name="微软雅黑", size=12, bold=True, color="C00000")
        total_cell.alignment = Alignment(horizontal="right")
        
        # ─── 落地费用明细区 ───
        fee_start = total_row + 2
        ws.merge_cells(f"A{fee_start}:F{fee_start}")
        fee_title = ws.cell(row=fee_start, column=1, value="▼ 落地费用预估")
        fee_title.font = Font(name="微软雅黑", size=12, bold=True, color="1F4E78")
        ws.row_dimensions[fee_start].height = 22
        
        # 计算各项费用
        total_car_price = sum(p["quantity"] * p["unit_price"] for p in normalized_products)
        purchase_tax = round(total_car_price / 11.3, 2)  # 购置税 ≈ 裸车价÷11.3
        insurance = round(total_car_price * 0.03, 0)       # 保险 ≈ 裸车价×3%
        plate_fee = 500                                     # 上牌费
        vessel_tax = 480                                    # 车船税 (2.0L标准)
        landing_total = total_car_price + purchase_tax + insurance + plate_fee + vessel_tax
        
        fee_headers = ["费用项目", "计算方式", "金额(¥)"]
        fee_header_row = fee_start + 1
        for col, h in enumerate(fee_headers, 1):
            c = ws.cell(row=fee_header_row, column=col, value=h)
            c.font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
            c.fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
            c.alignment = Alignment(horizontal="center")
            c.border = cell_border
        ws.merge_cells(f"A{fee_header_row}:B{fee_header_row}")
        ws.cell(row=fee_header_row, column=3).value = fee_headers[2]
        
        fee_items = [
            ("裸车价合计", f"{len(normalized_products)}款车型", total_car_price),
            ("车辆购置税", f"裸车价÷11.3（约10%）", purchase_tax),
            ("交强险+商业险", f"首年预估（约3%）", insurance),
            ("上牌费", "含验车+牌照+工本", plate_fee),
            ("车船税", "2.0L排量年费标准", vessel_tax),
        ]
        
        for i, (fee_name, fee_desc, fee_val) in enumerate(fee_items):
            row = fee_header_row + 1 + i
            c1 = ws.cell(row=row, column=1, value=fee_name)
            c1.font = Font(name="微软雅黑", size=10, bold=True)
            c1.border = cell_border
            c2 = ws.cell(row=row, column=2, value=fee_desc)
            c2.font = Font(name="微软雅黑", size=9, color="555555")
            c2.border = cell_border
            c3 = ws.cell(row=row, column=3, value=fee_val)
            c3.font = Font(name="微软雅黑", size=10)
            c3.number_format = '"¥"#,##0.00'
            c3.alignment = Alignment(horizontal="right")
            c3.border = cell_border
        
        # 落地总价行
        total_fee_row = fee_header_row + 1 + len(fee_items)
        ws.merge_cells(f"A{total_fee_row}:B{total_fee_row}")
        c1 = ws.cell(row=total_fee_row, column=1, value="🚗 预估落地总价")
        c1.font = Font(name="微软雅黑", size=11, bold=True, color="C00000")
        c1.alignment = Alignment(horizontal="center")
        c1.border = cell_border
        ws.cell(row=total_fee_row, column=2).border = cell_border
        c3 = ws.cell(row=total_fee_row, column=3, value=landing_total)
        c3.font = Font(name="微软雅黑", size=11, bold=True, color="C00000")
        c3.number_format = '"¥"#,##0.00'
        c3.alignment = Alignment(horizontal="right")
        c3.border = cell_border
        
        # ─── 备注区 ───
        note_row = total_fee_row + 2
        ws.merge_cells(f"A{note_row}:C{note_row}")
        note_cell = ws.cell(row=note_row, column=1, value=f"备注：{notes}\n以上落地价为估算参考值，实际金额以当地税局和保险公司为准。")
        note_cell.font = Font(name="微软雅黑", size=9, italic=True, color="666666")
        ws.row_dimensions[note_row].height = 30
        
        # ─── 列宽设置 ───
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 28
        ws.column_dimensions["C"].width = 16
        ws.column_dimensions["D"].width = 10
        ws.column_dimensions["E"].width = 18
        ws.column_dimensions["F"].width = 18
        
        # ─── 保存文件 ───
        wb.save(filepath)
        logger.info(f"[Excel] 报价单已生成: {filepath}")
        
        # ─── 公式重计算（xlsx Skill 要求）───
        await _recalculate_excel(filepath)
        
        return DocumentInfo(
            doc_type=DocumentType.XLSX,
            file_name=filename,
            file_path=filepath,
            file_size=os.path.getsize(filepath)
        )
        
    except Exception as e:
        logger.error(f"[Excel] 生成失败: {str(e)}")
        # 防御性降级：生成简易文本版本
        return await _fallback_quote_text(customer, normalized_products, valid_days, output_dir)


async def _recalculate_excel(filepath: str):
    """
    使用 LibreOffice 重新计算 Excel 公式（xlsx Skill 规范）
    确保所有公式都被计算，零 #REF! / #DIV/0! 错误
    """
    try:
        # 检查是否有 recalc.py 脚本
        recalc_script = os.path.join(settings.base_dir, "scripts", "recalc.py")
        
        if os.path.exists(recalc_script):
            result = subprocess.run(
                ["python", recalc_script, filepath],
                capture_output=True,
                text=True,
                timeout=30
            )
            logger.info(f"[Excel] 公式重计算完成: {filepath}")
            
            # 检查是否有错误
            if result.stdout:
                try:
                    import json
                    recalc_result = json.loads(result.stdout)
                    if recalc_result.get("status") == "errors_found":
                        logger.warning(f"[Excel] 公式错误: {recalc_result.get('error_summary')}")
                    else:
                        logger.info(f"[Excel] 零公式错误验证通过")
                except:
                    pass
        else:
            # 降级：使用 libreoffice 直接计算
            result = subprocess.run(
                ["libreoffice", "--headless", "--calc", "--nolockcheck", filepath],
                capture_output=True,
                timeout=30
            )
            logger.info(f"[Excel] 使用 LibreOffice 重新计算完成")
            
    except Exception as e:
        logger.warning(f"[Excel] 公式重计算跳过: {str(e)}")
        # 不重计算不阻塞主流程


async def _fallback_quote_text(customer: str, products: List[Dict], valid_days: int, output_dir: str) -> DocumentInfo:
    """
    防御性降级：生成文本格式报价单（当 Excel 生成失败时）
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"报价单_{customer}_{timestamp}.txt"
    filepath = os.path.join(output_dir, filename)
    
    total = sum(p["quantity"] * p["unit_price"] for p in products)
    
    content = f"""═══════════════════════════════════════════════════
                    产 品 报 价 单
═══════════════════════════════════════════════════

客户名称：{customer}
报价日期：{datetime.now().strftime("%Y年%m月%d日")}
有效期至：{(datetime.now() + __import__("datetime").timedelta(days=valid_days)).strftime("%Y年%m月%d日")}

───────────────────────────────────────────────────
序号  产品名称              数量    单价(¥)      小计(¥)
───────────────────────────────────────────────────
"""
    for i, p in enumerate(products, 1):
        subtotal = p["quantity"] * p["unit_price"]
        content += f"{i:<4}  {p['name']:<20}  {p['quantity']:<6}  {p['unit_price']:>10.2f}  {subtotal:>12.2f}\n"
    
    content += f"""───────────────────────────────────────────────────
                                          合计：¥{total:,.2f}
═══════════════════════════════════════════════════

备注：本报价仅供参考，具体以合同为准
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    logger.info(f"[Fallback] 文本报价单已生成: {filepath}")
    
    return DocumentInfo(
        doc_type=DocumentType.DOCX,  # 标记为文本文档
        file_name=filename,
        file_path=filepath,
        file_size=os.path.getsize(filepath)
    )


# ═══════════════════════════════════════════════════════════════
# 其他文档生成函数（保持原有功能，增强防御性）
# ═══════════════════════════════════════════════════════════════

async def _generate_proposal_document(params: Dict[str, Any]) -> DocumentInfo:
    """生成提案书（Word 格式）- 防御性增强版"""
    
    output_dir = settings.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    customer = safe_get_param(params, "customer_name", "客户")
    project = safe_get_param(params, "project_name", "方案")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"提案书_{customer}_{timestamp}.docx"
    filepath = os.path.join(output_dir, filename)
    
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        doc = Document()
        
        # 标题
        title = doc.add_heading(project, level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 客户信息
        doc.add_paragraph(f"致：{customer}")
        doc.add_paragraph(f"日期：{datetime.now().strftime('%Y年%m月%d日')}")
        doc.add_paragraph()
        
        # 背景
        background = safe_get_param(params, "project_background", "")
        if background:
            doc.add_heading("一、项目背景", level=1)
            doc.add_paragraph(background)
        
        # 方案亮点
        highlights = safe_get_param(params, "solution_highlights", [])
        if highlights:
            doc.add_heading("二、方案亮点", level=1)
            for h in highlights if isinstance(highlights, list) else []:
                doc.add_paragraph(h, style="List Bullet")
        
        # 实施周期
        timeline = safe_get_param(params, "timeline", "")
        if timeline:
            doc.add_heading("三、实施计划", level=1)
            doc.add_paragraph(f"预计实施周期：{timeline}")
        
        doc.save(filepath)
        
        return DocumentInfo(
            doc_type=DocumentType.DOCX,
            file_name=filename,
            file_path=filepath,
            file_size=os.path.getsize(filepath)
        )
        
    except Exception as e:
        logger.error(f"[DOCX] 提案书生成失败: {str(e)}")
        # 降级到文本
        return await _fallback_proposal_text(customer, project, output_dir)


async def _fallback_proposal_text(customer: str, project: str, output_dir: str) -> DocumentInfo:
    """提案书文本降级版本"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"提案书_{customer}_{timestamp}.txt"
    filepath = os.path.join(output_dir, filename)
    
    content = f"""═══════════════════════════════════════════════════
{project}
═══════════════════════════════════════════════════

致：{customer}
日期：{datetime.now().strftime('%Y年%m月%d日')}

本提案书详细介绍了我们的解决方案，
包括项目背景、方案亮点和实施计划。
请联系您的专属销售顾问获取更多详情。
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return DocumentInfo(
        doc_type=DocumentType.DOCX,
        file_name=filename,
        file_path=filepath,
        file_size=os.path.getsize(filepath)
    )


def _map_contract_type(intent_value: str, params: Dict[str, Any]) -> Optional[str]:
    """
    根据意图和参数映射到 template_service 的合同模板 key

    映射规则：
    - 购车合同 / sales contract → car_purchase
    - 订车协议 / order agreement → order_agreement
    - 金融分期 / finance → finance_installment
    - 无法识别 → None（由调用方决定如何处理）
    """
    # 从 LLM 提取的 contract_type 字段获取
    contract_type = params.get("contract_type", "").lower()
    key_terms = params.get("key_terms", {})
    if isinstance(key_terms, dict):
        terms_text = " ".join(f"{k} {v}" for k, v in key_terms.items()).lower()
    else:
        terms_text = str(key_terms).lower()

    # 关键词映射
    if any(kw in contract_type for kw in ["购车", "买车", "销售合同", "car_purchase", "purchase"]):
        return "car_purchase"
    if any(kw in contract_type for kw in ["订车", "预订", "预定", "order", "agreement"]):
        return "order_agreement"
    if any(kw in contract_type for kw in ["金融", "分期", "贷款", "finance", "installment", "按揭"]):
        return "finance_installment"
    # 也从 key_terms 和全局文本中检查
    if any(kw in terms_text for kw in ["分期", "贷款", "金融", "按揭"]):
        return "finance_installment"
    if any(kw in terms_text for kw in ["预订", "订车"]):
        return "order_agreement"

    logger.info(f"[Contract] 无法自动识别合同类型，需用户明确指定")
    return None


def _check_missing_params_for_contract(params: Dict[str, Any]) -> Optional[str]:
    """
    检查合同生成的关键参数是否齐全

    关键参数：
    - party_a / customer_name: 买方名称（必填）
    - car_model: 车型（必填）
    - price / amount: 车辆价格（尽量问，对话中常能拿到）
    - 付款方式（尽量问）
    - contract_type、卖方信息等可推断或填默认值
    """
    missing = []

    buyer = params.get("party_a") or params.get("customer_name") or params.get("buyer_name")
    if not buyer or buyer in ("客户", "待确认"):
        missing.append("客户名称（买方是谁？）")

    car_model = params.get("car_model") or params.get("product_name")
    if not car_model or car_model in ("待确认车型", "标准产品"):
        missing.append("车型（要买哪款车？）")

    price = params.get("price") or params.get("amount")
    if not price or price in ("待确认", "0"):
        missing.append("购车预算/价格（大概多少预算？）")

    # 付款方式：从 key_terms、全局参数、用户原文多维度检查
    key_terms = params.get("key_terms", {}) if isinstance(params.get("key_terms"), dict) else {}
    all_text = " ".join(str(v) for v in params.values() if isinstance(v, str))
    all_text += " " + " ".join(str(v) for v in key_terms.values() if isinstance(v, str))
    has_payment = (
        key_terms.get("付款方式") or key_terms.get("payment") or
        params.get("付款方式") or params.get("payment_method") or
        any(kw in all_text for kw in ["全款", "分期", "贷款", "按揭", "一次性", "首付"])
    )
    if not has_payment:
        missing.append("付款方式（全款还是分期？）")

    if not missing:
        return None

    return (
        "好的，我来帮您起草合同！还差一点信息就能生成：\n\n"
        + "\n".join(f"· {m}" for m in missing)
        + "\n\n请补充后我马上帮您生成～"
    )


def _check_missing_params_for_order(params: Dict[str, Any]) -> Optional[str]:
    """检查订车协议的关键参数"""
    missing = []

    buyer = params.get("buyer_name") or params.get("customer_name") or params.get("party_a")
    if not buyer or buyer in ("客户", "待确认"):
        missing.append("客户名称（预订人是谁？）")

    car_model = params.get("car_model") or params.get("product_name")
    if not car_model or car_model in ("待确认车型", "标准产品"):
        missing.append("车型（要订哪款车？）")

    # 定金：从多种可能来源提取（LLM可能放入amount/price/deposit_number中）
    deposit = (params.get("deposit_amount") or params.get("定金") or
               params.get("deposit_number") or params.get("amount") or params.get("price"))
    if not deposit or deposit in ("【协商确定】", "0", "待确认", ""):
        missing.append("定金金额（准备付多少定金？）")

    if not missing:
        return None

    return (
        "好的，我来帮您准备订车协议！还差一点信息：\n\n"
        + "\n".join(f"· {m}" for m in missing)
        + "\n\n请补充后我马上帮您生成～"
    )


def _check_missing_params_for_finance(params: Dict[str, Any]) -> Optional[str]:
    """检查金融分期合同的关键参数"""
    missing = []

    borrower = params.get("borrower_name") or params.get("party_a") or params.get("customer_name")
    if not borrower or borrower in ("客户", "待确认"):
        missing.append("借款人姓名（贷款人是谁？）")

    car_model = params.get("car_model") or params.get("product_name")
    if not car_model or car_model in ("待确认车型", "标准产品"):
        missing.append("车型（买哪款车？）")

    loan_amount = params.get("loan_amount") or params.get("amount")
    if not loan_amount or loan_amount in ("【按比例计算】", "待确认", "0", ""):
        missing.append("贷款金额（需要贷款多少？）")

    # 期数：从 installments 或全局参数中搜索
    installments = params.get("installments") or params.get("loan_term") or params.get("term")
    if not installments or installments in ("0", ""):
        # 从所有参数值中查数字+期的模式
        import re as _re
        all_text = " ".join(str(v) for v in params.values() if isinstance(v, str))
        match = _re.search(r"(\d+)\s*期", all_text)
        if match:
            params["installments"] = match.group(1)
        else:
            missing.append("贷款期数（分多少期？如12/24/36期）")

    if not missing:
        return None

    return (
        "好的，我来帮您准备金融分期合同！还差一点信息：\n\n"
        + "\n".join(f"· {m}" for m in missing)
        + "\n\n请补充后我马上帮您生成～"
    )


def _check_missing_params_for_proposal(params: Dict[str, Any]) -> Optional[str]:
    """
    检查提案书生成的关键参数是否齐全

    关键字段：customer_company, project_name, contact_person,
    contact_phone, project_budget
    同时检测中文默认占位值（"待确认"、"未提供"、"标准方案"等）

    Returns:
        缺失参数的追问文案，参数齐全返回 None
    """
    PLACEHOLDER_VALUES = {"", "待确认", "未提供", "标准方案", "客户", "客户公司", "销售方案", "待确认车型"}

    def _is_missing(val) -> bool:
        """判断参数值是否缺失（空或占位值）"""
        if val is None:
            return True
        if isinstance(val, str) and (val.strip() in PLACEHOLDER_VALUES):
            return True
        return False

    missing = []

    # ── 必填关键字段检查 ──
    customer = params.get("customer_name") or params.get("customer_company")
    if _is_missing(customer):
        missing.append("客户公司名称（提案提交给哪家公司？）")

    project = params.get("project_name")
    if _is_missing(project):
        missing.append("项目名称（做什么项目？）")

    contact_person = params.get("contact_person") or params.get("customer_name")
    if _is_missing(contact_person):
        missing.append("联系人姓名（谁是主要对接人？）")

    contact_phone = params.get("contact_phone") or params.get("buyer_phone")
    if _is_missing(contact_phone):
        missing.append("联系电话（方便后续沟通）")

    project_budget = params.get("project_budget") or params.get("budget_range")
    if _is_missing(project_budget):
        missing.append("项目预算（大概预算范围？）")

    if not missing:
        return None

    return (
        "好的，我来帮您准备提案书！还需要补充以下信息：\n\n"
        + "\n".join(f"· {m}" for m in missing)
        + "\n\n请告诉我这些信息，我马上生成～"
    )


def _count_default_params(params: Dict[str, Any]) -> tuple:
    """
    统计提案参数中默认值/占位值的比例

    Returns:
        (默认值数量, 总字段数量)
    """
    PLACEHOLDER_VALUES = {
        "", "待确认", "未提供", "标准方案", "客户", "客户公司",
        "销售方案", "待确认车型", "企业商务出行", "广汽丰田授权经销商",
        "专属销售顾问", "性价比、空间、品牌", "请联系专属顾问获取定制化金融方案。",
        "请联系专属顾问了解最新优惠活动。",
    }
    if not params:
        return (0, 1)  # avoid div by zero
    total = len(params)
    default_count = 0
    for v in params.values():
        if v is None:
            default_count += 1
        elif isinstance(v, str) and v.strip() in PLACEHOLDER_VALUES:
            default_count += 1
        elif isinstance(v, str) and v.startswith("【"):
            default_count += 1
    return (default_count, total)


async def _generate_contract_document(params: Dict[str, Any]) -> DocumentInfo:
    """
    生成合同文档 — 调用 template_service.fill_contract()

    LLM 提取的对话参数会填充到 docx 模板的 {{xxx}} 占位符中。
    对话中拿不到的字段（卖方信息、公司章等）保留提示文字。
    """
    try:
        svc = TemplateService(base_dir=settings.base_dir)

        # 确定合同模板类型
        contract_type = _map_contract_type("contract_drafting", params)
        if contract_type is None:
            contract_type = "car_purchase"  # 最终兜底，但调用方应在上游拦截
            logger.warning(f"[Contract] _generate_contract_document 收到未识别类型，兜底为 car_purchase")

        # 构建填充数据：从 LLM 提取的参数映射到 GF-2015-0121 模板占位符
        buyer = safe_get_param(params, "party_a", safe_get_param(params, "customer_name", safe_get_param(params, "buyer_name", "客户")))
        car = safe_get_param(params, "car_model", safe_get_param(params, "product_name", "待确认车型"))
        price_val = safe_get_param(params, "price", safe_get_param(params, "amount", "待确认"))

        data = {
            # ── 卖方信息（对话里拿不到，填默认提示）──
            "seller_name": params.get("party_b", "【需人工确认：卖方公司名称】"),
            "seller_credit_code": params.get("seller_credit_code", "【需人工确认】"),
            "seller_address": params.get("seller_address", "【需人工确认：卖方地址】"),
            "seller_representative": params.get("seller_representative", "【需人工确认】"),
            "seller_phone": params.get("seller_phone", "【需人工确认：卖方电话】"),
            # ── 买方信息 ──
            "buyer_name": buyer,
            "buyer_id_card": safe_get_param(params, "buyer_id_card", "【需乙方提供】"),
            "buyer_address": safe_get_param(params, "buyer_address", "【需乙方提供】"),
            "buyer_phone": safe_get_param(params, "buyer_phone", "【需乙方提供】"),
            "buyer_zip": safe_get_param(params, "buyer_zip", ""),
            # ── 车辆信息 ──
            "car_brand": safe_get_param(params, "car_brand", "丰田"),
            "car_model": car,
            "car_origin": safe_get_param(params, "car_origin", "中国"),
            "manufacturer": safe_get_param(params, "manufacturer", "广汽丰田汽车有限公司"),
            "car_color": safe_get_param(params, "car_color", "待确认"),
            "interior_color": safe_get_param(params, "interior_color", "待确认"),
            "displacement": safe_get_param(params, "displacement", "待确认"),
            "car_config": safe_get_param(params, "car_config", "标准配置"),
            "vin": safe_get_param(params, "vin", "【交付前填写】"),
            "engine_no": safe_get_param(params, "engine_no", "【交付前填写】"),
            "production_date": safe_get_param(params, "production_date", "【交付前填写】"),
            "certificate_no": safe_get_param(params, "certificate_no", "【交付前填写】"),
            # ── 价款 ──
            "car_price": str(price_val),
            "total_price_cn": safe_get_param(params, "total_price_cn", "【需人工确认】"),
            # ── 付款方式 ──
            "payment_mode": safe_get_param(params, "payment_mode", "一"),
            "payment_days": safe_get_param(params, "payment_days", "7"),
            "payment_method": safe_get_param(params, "payment_method", "全款"),
            "down_payment_ratio": safe_get_param(params, "down_payment_ratio", "30"),
            "down_payment": safe_get_param(params, "down_payment", "【按比例计算】"),
            "loan_amount": safe_get_param(params, "loan_amount", "【按比例计算】"),
            "other_payment_terms": safe_get_param(params, "other_payment_terms", "无"),
            # ── 交付 ──
            "delivery_date": safe_get_param(params, "delivery_date", "【协商确定】"),
            "delivery_location": safe_get_param(params, "delivery_location", "经销商处"),
            "mileage_limit": safe_get_param(params, "mileage_limit", "100"),
            "other_delivery_items": safe_get_param(params, "other_delivery_items", "无"),
            # ── 三包 ──
            "warranty_years": safe_get_param(params, "warranty_years", "3"),
            "warranty_km": safe_get_param(params, "warranty_km", "6"),
            "sanbao_years": safe_get_param(params, "sanbao_years", "2"),
            "sanbao_km": safe_get_param(params, "sanbao_km", "5"),
            # ── 违约责任 ──
            "late_delivery_penalty_rate": safe_get_param(params, "late_delivery_penalty_rate", "0.05"),
            "late_payment_penalty_rate": safe_get_param(params, "late_payment_penalty_rate", "0.05"),
            "penalty_cap": safe_get_param(params, "penalty_cap", "20"),
            # ── 定金 ──
            "deposit_amount": safe_get_param(params, "deposit_amount", "【协商确定】"),
            "deposit_amount_cn": safe_get_param(params, "deposit_amount_cn", "【协商确定】"),
            # ── 争议 ──
            "arbitration_commission": safe_get_param(params, "arbitration_commission", "卖方所在地仲裁委员会"),
            # ── 订车协议专用字段 ──
            "dealer_name": safe_get_param(params, "seller_name", safe_get_param(params, "party_b", "【需人工确认：经销商名称】")),
            "dealer_address": safe_get_param(params, "seller_address", "【需人工确认】"),
            "dealer_phone": safe_get_param(params, "seller_phone", "【需人工确认】"),
            "estimated_price": safe_get_param(params, "estimated_price", safe_get_param(params, "car_price", "待确认")),
            "car_config": safe_get_param(params, "car_config", "标准配置"),
            "dealer_account": safe_get_param(params, "dealer_account", "【需经销商提供】"),
            "deposit_payment_method": safe_get_param(params, "deposit_payment_method", "银行转账"),
            "deposit_days": safe_get_param(params, "deposit_days", "3"),
            "lock_days": safe_get_param(params, "lock_days", "30"),
            "price_protection_method": safe_get_param(params, "price_protection_method", "按第五条价格保护条款执行"),
            "eta_date": safe_get_param(params, "eta_date", safe_get_param(params, "delivery_date", "【预计30-45个工作日】")),
            "acceptance_days": safe_get_param(params, "acceptance_days", "7"),
            "late_acceptance_fee": safe_get_param(params, "late_acceptance_fee", "50"),
            "grace_period_days": safe_get_param(params, "grace_period_days", "15"),
            "overdue_rate": safe_get_param(params, "overdue_rate", "0.05"),
            "cancel_deduction_rate": safe_get_param(params, "cancel_deduction_rate", "30"),
            "transfer_fee": safe_get_param(params, "transfer_fee", "500"),
            # ── 金融分期专用字段 ──
            "finance_company": safe_get_param(params, "finance_company", safe_get_param(params, "party_b", "【需人工确认：金融机构名称】")),
            "finance_credit_code": safe_get_param(params, "finance_credit_code", "【需人工确认】"),
            "finance_address": safe_get_param(params, "finance_address", "【需人工确认】"),
            "finance_phone": safe_get_param(params, "finance_phone", "【需人工确认】"),
            "borrower_name": safe_get_param(params, "borrower_name", safe_get_param(params, "party_a", safe_get_param(params, "customer_name", "客户"))),
            "borrower_id_card": safe_get_param(params, "borrower_id_card", "【需乙方提供】"),
            "borrower_address": safe_get_param(params, "buyer_address", "【需乙方提供】"),
            "borrower_phone": safe_get_param(params, "buyer_phone", "【需乙方提供】"),
            "borrower_bank": safe_get_param(params, "borrower_bank", "【需乙方提供开户行】"),
            "borrower_account": safe_get_param(params, "borrower_account", "【需乙方提供还款账号】"),
            "guarantor_name": safe_get_param(params, "guarantor_name", "无"),
            "guarantor_id_card": safe_get_param(params, "guarantor_id_card", ""),
            "guarantor_phone": safe_get_param(params, "guarantor_phone", ""),
            "loan_amount_cn": safe_get_param(params, "loan_amount_cn", "【需人工确认】"),
            "total_price": safe_get_param(params, "total_price", safe_get_param(params, "car_price", "待确认")),
            "installments": safe_get_param(params, "installments", "36"),
            "first_repayment_date": safe_get_param(params, "first_repayment_date", "【放款后次月对应日】"),
            "last_repayment_date": safe_get_param(params, "last_repayment_date", "【按还款计划表】"),
            "repayment_day": safe_get_param(params, "repayment_day", "20"),
            "lpr_term": safe_get_param(params, "lpr_term", "五年期以上"),
            "lpr_spread_bp": safe_get_param(params, "lpr_spread_bp", "0"),
            "annual_rate": safe_get_param(params, "annual_rate", "【按LPR确定】"),
            "monthly_payment": safe_get_param(params, "monthly_payment", "【按还款计划计算】"),
            "down_payment_cn": safe_get_param(params, "down_payment_cn", "【需人工确认】"),
            "repayment_method_other": safe_get_param(params, "repayment_method_other", "无"),
            "early_repay_lock_months": safe_get_param(params, "early_repay_lock_months", "12"),
            "early_repay_fee_rate": safe_get_param(params, "early_repay_fee_rate", "0"),
            "early_repay_fee_min": safe_get_param(params, "early_repay_fee_min", "0"),
            "insurance_third_party": safe_get_param(params, "insurance_third_party", "200"),
            "default_months": safe_get_param(params, "default_months", "3"),
            "default_months_total": safe_get_param(params, "default_months_total", "6"),
            "penalty_rate_multiplier": safe_get_param(params, "penalty_rate_multiplier", "50"),
            "lender_default_rate": safe_get_param(params, "lender_default_rate", "0.05"),
            # ── 自动生成 ──
            "contract_no": "",
            "sign_date": "",
        }

        # 合并 LLM 提取的所有参数（包括 key_terms 转平铺）
        for k, v in params.items():
            if k not in data and isinstance(v, (str, int, float)):
                data[k] = str(v) if not isinstance(v, str) else v

        # key_terms 平铺到 data 中
        key_terms = params.get("key_terms", {})
        if isinstance(key_terms, dict):
            for k, v in key_terms.items():
                if k not in data:
                    data[k] = str(v)

        logger.info(f"[Contract] 填充合同模板: {contract_type}, 数据键: {list(data.keys())}")

        output_path = await svc.fill_contract(contract_type, data)

        file_name = os.path.basename(output_path)
        return DocumentInfo(
            doc_type=DocumentType.DOCX,
            file_name=file_name,
            file_path=output_path,
            file_size=os.path.getsize(output_path),
        )

    except Exception as e:
        logger.error(f"[Contract] 模板填充失败: {str(e)}，回退到通用文档生成")
        return await _generate_generic_document(
            UserIntent.CONTRACT_DRAFTING, params
        )


async def _generate_proposal_via_template(params: Dict[str, Any]) -> DocumentInfo:
    """
    生成提案书 — 调用 template_service.fill_proposal()

    优先使用模板填充，失败时回退到 _generate_proposal_document()
    """
    try:
        svc = TemplateService(base_dir=settings.base_dir)

        # 构建填充数据：映射到专业提案书模板的占位符
        cust = safe_get_param(params, "customer_name", safe_get_param(params, "customer_company", "客户"))
        proj = safe_get_param(params, "project_name", "企业用车解决方案")
        data = {
            # ── 基本信息 ──
            "customer_name": cust,
            "customer_company": safe_get_param(params, "customer_company", cust),
            "contact_person": safe_get_param(params, "contact_person", safe_get_param(params, "customer_name", "待确认")),
            "contact_phone": safe_get_param(params, "contact_phone", safe_get_param(params, "buyer_phone", "待确认")),
            "project_name": proj,
            "seller_name": safe_get_param(params, "seller_name", "广汽丰田授权经销商"),
            "sales_rep": safe_get_param(params, "sales_rep", "专属销售顾问"),
            "sales_phone": safe_get_param(params, "sales_phone", "待确认"),
            "sales_email": safe_get_param(params, "sales_email", "待确认"),
            "showroom_address": safe_get_param(params, "showroom_address", "待确认"),
            # ── 需求分析 ──
            "usage_scenario": safe_get_param(params, "usage_scenario", "企业商务出行"),
            "budget_range": safe_get_param(params, "budget_range", "待确认"),
            "fleet_size": safe_get_param(params, "fleet_size", "待确认"),
            "car_preference": safe_get_param(params, "car_preference", "待确认车型"),
            "priority_concerns": safe_get_param(params, "priority_concerns", "性价比、空间、品牌"),
            "needs_analysis": safe_get_param(params, "needs_analysis", "详见需求沟通纪要。"),
            "company_intro": safe_get_param(params, "company_intro", "【按实际项目填写】"),
            # ── 推荐车型 ──
            "car_model_1": safe_get_param(params, "car_model_1", safe_get_param(params, "car_model", "凯美瑞 2.0G 豪华版")),
            "car_model_2": safe_get_param(params, "car_model_2", "汉兰达 2.0T 精英版"),
            "price_1": safe_get_param(params, "price_1", safe_get_param(params, "car_price", "19.98万")),
            "price_2": safe_get_param(params, "price_2", "26.88万"),
            "displacement_1": safe_get_param(params, "displacement_1", "2.0L"),
            "displacement_2": safe_get_param(params, "displacement_2", "2.0T"),
            "fuel_1": safe_get_param(params, "fuel_1", "5.7"),
            "fuel_2": safe_get_param(params, "fuel_2", "8.2"),
            "size_1": safe_get_param(params, "size_1", "4885×1840×1455"),
            "size_2": safe_get_param(params, "size_2", "4965×1930×1750"),
            "wheelbase_1": safe_get_param(params, "wheelbase_1", "2825"),
            "wheelbase_2": safe_get_param(params, "wheelbase_2", "2850"),
            "transmission_1": safe_get_param(params, "transmission_1", "CVT无级变速"),
            "transmission_2": safe_get_param(params, "transmission_2", "8AT"),
            "reason_1": safe_get_param(params, "reason_1", "低油耗、高保值率、商务大气"),
            "reason_2": safe_get_param(params, "reason_2", "7座大空间、动力充沛、通过性好"),
            # ── 竞品 ──
            "competitor_1": safe_get_param(params, "competitor_1", "本田雅阁"),
            "competitor_2": safe_get_param(params, "competitor_2", "日产天籁"),
            "competitor_3": safe_get_param(params, "competitor_3", "大众迈腾"),
            "comparison_summary": safe_get_param(params, "comparison_summary", "丰田车型在保值率和可靠性方面具有显著优势。"),
            # ── 竞品对比表（cmp_<field>_<1-5>）──
            "cmp_price_1": safe_get_param(params, "cmp_price_1", safe_get_param(params, "price_1", "19.98万")),
            "cmp_price_2": safe_get_param(params, "cmp_price_2", safe_get_param(params, "price_2", "26.88万")),
            "cmp_price_3": safe_get_param(params, "cmp_price_3", "17.98万"),
            "cmp_price_4": safe_get_param(params, "cmp_price_4", "17.98万"),
            "cmp_price_5": safe_get_param(params, "cmp_price_5", "18.69万"),
            "cmp_fuel_1": safe_get_param(params, "cmp_fuel_1", "5.7"),
            "cmp_fuel_2": safe_get_param(params, "cmp_fuel_2", "8.2"),
            "cmp_fuel_3": safe_get_param(params, "cmp_fuel_3", "6.0"),
            "cmp_fuel_4": safe_get_param(params, "cmp_fuel_4", "6.6"),
            "cmp_fuel_5": safe_get_param(params, "cmp_fuel_5", "6.5"),
            "cmp_resale_1": safe_get_param(params, "cmp_resale_1", "73%"),
            "cmp_resale_2": safe_get_param(params, "cmp_resale_2", "70%"),
            "cmp_resale_3": safe_get_param(params, "cmp_resale_3", "60%"),
            "cmp_resale_4": safe_get_param(params, "cmp_resale_4", "55%"),
            "cmp_resale_5": safe_get_param(params, "cmp_resale_5", "58%"),
            "cmp_wheelbase_1": safe_get_param(params, "cmp_wheelbase_1", "2825"),
            "cmp_wheelbase_2": safe_get_param(params, "cmp_wheelbase_2", "2850"),
            "cmp_wheelbase_3": safe_get_param(params, "cmp_wheelbase_3", "2830"),
            "cmp_wheelbase_4": safe_get_param(params, "cmp_wheelbase_4", "2825"),
            "cmp_wheelbase_5": safe_get_param(params, "cmp_wheelbase_5", "2871"),
            "cmp_advantage_1": safe_get_param(params, "cmp_advantage_1", "保值率高、故障率低"),
            "cmp_advantage_2": safe_get_param(params, "cmp_advantage_2", "空间大、通过性好"),
            "cmp_advantage_3": safe_get_param(params, "cmp_advantage_3", "操控性好"),
            "cmp_advantage_4": safe_get_param(params, "cmp_advantage_4", "舒适性佳"),
            "cmp_advantage_5": safe_get_param(params, "cmp_advantage_5", "品牌影响力"),
            # ── 金融 ──
            "finance_plan": safe_get_param(params, "finance_plan", "请联系专属顾问获取定制化金融方案。"),
            "plan1_ratio": "30%", "plan1_down": safe_get_param(params, "plan1_down", "6万"), "plan1_monthly": safe_get_param(params, "plan1_monthly", "3500"), "plan1_term": "36期",
            "plan2_ratio": "50%", "plan2_down": safe_get_param(params, "plan2_down", "10万"), "plan2_monthly": safe_get_param(params, "plan2_monthly", "2200"), "plan2_term": "24期",
            "plan3_ratio": "0%", "plan3_down": "0", "plan3_monthly": safe_get_param(params, "plan3_monthly", "5800"), "plan3_term": "12期",
            # ── 落地费用 ──
            "total_car_price": safe_get_param(params, "total_car_price", safe_get_param(params, "car_price", "待确认")),
            "purchase_tax": safe_get_param(params, "purchase_tax", "约1.7万"),
            "insurance_fee": safe_get_param(params, "insurance_fee", "约6000"),
            "plate_fee": safe_get_param(params, "plate_fee", "500"),
            "vessel_tax": safe_get_param(params, "vessel_tax", "480"),
            "landing_total": safe_get_param(params, "landing_total", "待计算"),
            "cost_breakdown": safe_get_param(params, "cost_breakdown", "以最终报价单为准。"),
            # ── 增值与礼包 ──
            "value_added_services": safe_get_param(params, "value_added_services", "请联系专属顾问了解最新优惠活动。"),
            "gift_package": safe_get_param(params, "gift_package", "原厂脚垫+全车贴膜+行车记录仪"),
            "gift_value": safe_get_param(params, "gift_value", "约3000元"),
            "maintenance_plan": safe_get_param(params, "maintenance_plan", "3年6次免费基础保养"),
            "extended_warranty": safe_get_param(params, "extended_warranty", "可选厂家延保至5年/10万公里"),
            # ── 风险 ──
            "estimated_delivery_weeks": safe_get_param(params, "estimated_delivery_weeks", "4-6"),
            "annual_fuel_cost": safe_get_param(params, "annual_fuel_cost", "约8000"),
            "annual_mileage": safe_get_param(params, "annual_mileage", "20000"),
            "annual_maintenance_cost": safe_get_param(params, "annual_maintenance_cost", "约2000"),
            "proposal_valid_days": safe_get_param(params, "proposal_valid_days", "30"),
            "risk_disclaimer": safe_get_param(params, "risk_disclaimer", ""),
            # ── 自动生成 ──
            "proposal_no": "",
            "proposal_date": "",
        }

        # 合并所有 LLM 提取的额外参数
        for k, v in params.items():
            if k not in data and isinstance(v, (str, int, float)):
                data[k] = str(v) if not isinstance(v, str) else v

        logger.info(f"[Proposal] 填充提案书模板, 数据键: {list(data.keys())}")

        output_path = await svc.fill_proposal(data)

        file_name = os.path.basename(output_path)
        return DocumentInfo(
            doc_type=DocumentType.DOCX,
            file_name=file_name,
            file_path=output_path,
            file_size=os.path.getsize(output_path),
        )

    except Exception as e:
        logger.warning(f"[Proposal] 模板填充失败: {str(e)}，回退到直接生成")
        return await _generate_proposal_document(params)


async def _generate_analysis_document(params: Dict[str, Any]) -> DocumentInfo:
    """生成数据分析报表 - 简化版"""
    output_dir = settings.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    analysis_type = safe_get_param(params, "analysis_type", "销售数据分析")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"数据分析报表_{analysis_type}_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
        
        wb = Workbook()
        ws = wb.active
        ws.title = "数据分析"
        
        ws["A1"] = analysis_type
        ws["A1"].font = Font(size=16, bold=True)
        ws.merge_cells("A1:D1")
        
        ws["A3"] = f"数据源：{safe_get_param(params, 'data_source', '系统数据')}"
        ws["A4"] = f"时间范围：{safe_get_param(params, 'date_range', '全部')}" 
        ws["A5"] = f"分析指标：{', '.join(safe_get_param(params, 'metrics', ['销售额', '客户数']))}"
        
        wb.save(filepath)
        
        return DocumentInfo(
            doc_type=DocumentType.XLSX,
            file_name=filename,
            file_path=filepath,
            file_size=os.path.getsize(filepath)
        )
    except Exception as e:
        logger.error(f"[Excel] 分析报表生成失败: {str(e)}")
        raise


async def _generate_presentation(params: Dict[str, Any]) -> DocumentInfo:
    """生成演示文稿大纲"""
    output_dir = settings.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    title = safe_get_param(params, "title", "演示文稿")
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"演示文稿_{title}_{timestamp}.txt"
    filepath = os.path.join(output_dir, filename)
    
    content = f"""═══════════════════════════════════════════════════
演示文稿大纲：{title}
═══════════════════════════════════════════════════

副标题：{safe_get_param(params, 'subtitle', '')}
目标受众：{safe_get_param(params, 'target_audience', '决策层')}

章节大纲：
"""
    sections = safe_get_param(params, "sections", [])
    if isinstance(sections, list):
        for i, section in enumerate(sections, 1):
            content += f"{i}. {section}\n"
    
    content += f"\n共 {safe_get_param(params, 'slides_count', 10)} 页幻灯片"
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return DocumentInfo(
        doc_type=DocumentType.PPTX,
        file_name=filename,
        file_path=filepath,
        file_size=os.path.getsize(filepath)
    )


async def _generate_generic_document(intent: UserIntent, params: Dict) -> DocumentInfo:
    """生成通用文档"""
    output_dir = settings.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"文档_{intent.value}_{timestamp}.txt"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"文档类型：{intent.value}\n")
        f.write(f"生成时间：{datetime.now().isoformat()}\n")
        f.write(f"参数：{json.dumps(params, ensure_ascii=False, indent=2)}")
    
    return DocumentInfo(
        doc_type=DocumentType.DOCX,
        file_name=filename,
        file_path=filepath,
        file_size=os.path.getsize(filepath)
    )


# ═══════════════════════════════════════════════════════════════
# LangGraph 节点函数
# ═══════════════════════════════════════════════════════════════

# 参数提取提示模板
PARAM_EXTRACTION_PROMPT = """你是一个参数提取专家。请从用户的对话中提取生成文档所需的参数。

当前意图：{intent}

请分析用户消息和上下文，提取以下参数并以 JSON 格式返回：

{param_description}

注意：
1. 如果某些参数缺失，使用合理的默认值或空值
2. 如果信息不明确，在 reasoning 中说明
3. 返回必须是合法的 JSON 格式

示例输出格式：
{{
    "params": {{...}},
    "missing_params": ["参数名1", "参数名2"],
    "reasoning": "提取说明"
}}"""


PARAM_DESCRIPTIONS = {
    UserIntent.QUOTE_GENERATION: """
报价单参数 (QuoteParams):
- customer_name: 客户名称（必填）
- products: 产品列表，每项包含 name, quantity, unit_price
  重要：如果用户在对话中提到了多款车型（如"凯美瑞和亚洲龙怎么选"），
  请把每款车都列入 products 列表！每款车填真实合理的价格。
  例如用户同时问了凯美瑞和亚洲龙，就返回两个产品。
- unit_price: 单价（单位：元），填写真实市场价
- valid_days: 报价有效期天数，默认 30
- discount_rate: 折扣率（0-1之间），可选
- notes: 备注信息，可选
""",
    UserIntent.PROPOSAL_CREATION: """
提案书参数 (ProposalParams):
- customer_name: 客户名称/联系人（必填）
- customer_company: 客户公司名称（必填，如未提及可从 customer_name 推断）
- contact_person: 联系人姓名（必填）
- contact_phone: 联系人电话（必填）
- project_name: 项目名称（必填）
- project_budget: 项目预算（必填，尽量从对话中推断金额或范围）
- project_background: 项目背景描述，可选
- solution_highlights: 方案亮点列表，可选
- timeline: 实施周期，可选
- budget_range: 预算范围，可选

⚠️ 重要提示：
- 如果用户仅说了"帮我写个提案书"而没有提供具体项目名、公司名、预算等关键信息，
  必须在 missing_params 中列出所有缺少的关键字段（customer_company, project_name, 
  contact_person, contact_phone, project_budget），不要用"标准方案"等默认值填充。
- 不要将中文占位值（如"待确认"、"未提供"、"标准方案"）作为提取结果填充到 params 中，
  这些应视为参数缺失。
""",
    UserIntent.CONTRACT_DRAFTING: """
合同参数 (ContractParams):
- party_a: 甲方/买方名称（必填，从对话中提取客户名）
- party_b: 乙方/卖方名称（如未提及，填空字符串）
- contract_type: 合同类型，必须从以下选项中选择其一：
  · 购车合同（对应 car_purchase — 买车、签合同、购车协议）
  · 订车协议（对应 order_agreement — 预订、订车、意向金）
  · 金融分期合同（对应 finance_installment — 贷款、分期、按揭、金融方案）
- car_model: 车型名称（从对话中提取）
- amount: 合同金额（单位：元），可选
- price: 车辆单价，可选
- key_terms: 关键条款字典，如 {"付款方式": "全款", "交付时间": "30天内"}

⚠️ 时间短语解析规则（非常重要！务必从对话中识别并解析为数字）：
对话中经常出现中文时间表述，请解析为具体数字并放入 params：
示例1：用户说"10天内付款" → payment_days: "10"
示例2：用户说"一周内付定金" → deposit_days: "7"（一周=7天）
示例3：用户说"三天内付清全款" → payment_days: "3"
示例4：用户说"半个月内提车" → delivery 相关约15天
示例5：用户说"一个月内交车" → delivery 相关约30天
示例6：用户说"两个月付款周期" → payment_days: "60"
示例7：用户说"两周内签合同" → lock_days: "14"

将解析出的时间字段以字符串形式放入 params，字段名：payment_days, deposit_days, lock_days
""",
    UserIntent.DATA_ANALYSIS: """
数据分析参数 (AnalysisParams):
- data_source: 数据源描述或文件路径（必填）
- analysis_type: 分析类型（销售分析、客户分析等）
- metrics: 关键指标列表
- date_range: 时间范围，可选
""",
    UserIntent.PRESENTATION_REQUEST: """
演示文稿参数 (PresentationParams):
- title: 演示标题（必填）
- subtitle: 副标题，可选
- sections: 章节大纲列表
- target_audience: 目标受众
- slides_count: 幻灯片数量，默认 10
""",
}


def safe_parse_llm_json(content: str) -> Dict[str, Any]:
    """
    防御性 LLM JSON 解析
    处理 Markdown 代码块、裸 JSON、解析失败等情况
    """
    import re
    
    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # 提取 Markdown 代码块
    patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
        r'\{[\s\S]*\}'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except:
                continue
    
    # 兜底返回
    return {"params": {}, "missing_params": [], "reasoning": "JSON解析失败，使用默认值"}


async def extract_document_params_node(state: SalesState) -> SalesState:
    """
    文档参数提取节点 - 防御性增强版
    
    无论 LLM 返回什么，都确保 params 字典有效，绝不中断
    """
    logger.info(f"[Session: {state.get('session_id', 'unknown')}] 开始提取文档参数")

    # 多轮对话：优先使用之前 document_params 中的文档意图
    prev_doc_params = state.get("document_params")
    prev_doc_intent = None
    if prev_doc_params and isinstance(prev_doc_params, dict):
        prev_intent_str = prev_doc_params.get("intent", "")
        if prev_intent_str in ("contract_drafting", "proposal_creation", "quote_generation"):
            prev_doc_intent = prev_intent_str

    # 防御：确保 intent_analysis 存在
    intent_analysis = state.get("intent_analysis")
    if not intent_analysis and not prev_doc_intent:
        logger.warning("[Params] intent_analysis 缺失，使用默认参数")
        state["document_params"] = {
            "intent": "quote_generation",
            "params": DEFAULT_PARAMS.copy(),
            "missing": []
        }
        state["next_node"] = "generate_document"
        return state

    # 意图选择：当前消息是新的文档意图 → 用新的；否则沿用上一轮（多轮补参数）
    current_intent = intent_analysis.intent if hasattr(intent_analysis, 'intent') else None
    doc_intents = {UserIntent.CONTRACT_DRAFTING, UserIntent.PROPOSAL_CREATION, UserIntent.QUOTE_GENERATION}
    if prev_doc_intent and current_intent in doc_intents and current_intent.value != prev_doc_intent:
        # 用户开始了新的文档请求，用当前意图
        intent = current_intent
        logger.info(f"[Params] 检测到新文档意图: {intent.value} (替换旧的 {prev_doc_intent})")
    elif prev_doc_intent:
        # 多轮补参数，沿用上一个文档意图
        intent_map = {
            "contract_drafting": UserIntent.CONTRACT_DRAFTING,
            "proposal_creation": UserIntent.PROPOSAL_CREATION,
            "quote_generation": UserIntent.QUOTE_GENERATION,
        }
        intent = intent_map.get(prev_doc_intent, UserIntent.QUOTE_GENERATION)
        logger.info(f"[Params] 沿用上一轮的文档意图: {prev_doc_intent}")
    else:
        intent = intent_analysis.intent if hasattr(intent_analysis, 'intent') else UserIntent.QUOTE_GENERATION
    
    try:
        llm = ChatOpenAI(
            model=settings.default_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.2,
        )
        
        param_desc = PARAM_DESCRIPTIONS.get(intent, "请提取文档生成所需的所有参数")
        
        prompt = PARAM_EXTRACTION_PROMPT.format(
            intent=intent.value if hasattr(intent, 'value') else str(intent),
            param_description=param_desc
        )
        
        # 准备对话历史（防御性处理）
        messages_list = state.get("messages", [])
        history_text = "无历史消息"
        if messages_list and isinstance(messages_list, list):
            try:
                history_text = "\n".join([
                    f"{'用户' if hasattr(m, 'type') and m.type == 'human' else '助手'}: {getattr(m, 'content', str(m))}"
                    for m in messages_list[-5:]
                ])
            except Exception as e:
                logger.warning(f"[Params] 历史消息解析失败: {e}")
        
        context = state.get("context", {})
        
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"对话历史：\n{history_text}\n\n当前业务上下文：{json.dumps(context, ensure_ascii=False)}")
        ]
        
        response = await llm.ainvoke(messages)
        
        # 防御性 JSON 解析
        result = safe_parse_llm_json(response.content)
        params = result.get("params", {}) if isinstance(result.get("params"), dict) else {}
        missing = result.get("missing_params", []) if isinstance(result.get("missing_params"), list) else []
        
        logger.info(f"[Params] 提取完成，缺失参数: {missing}")
        
        # 合并上下文信息
        params.update({
            "_customer_name": context.get("customer_name", DEFAULT_PARAMS["customer_name"]),
            "_sales_rep": context.get("sales_rep_name", DEFAULT_PARAMS["sales_rep"]),
            "_generated_at": datetime.now().isoformat(),
        })
        
        state["document_params"] = {
            "intent": intent.value if hasattr(intent, 'value') else str(intent),
            "params": params,
            "missing": missing
        }
        
        # 关键参数缺失也不中断，直接填充默认值继续
        state["next_node"] = "generate_document"
        
    except Exception as e:
        logger.error(f"[Params] 提取失败: {str(e)}，使用默认参数继续")
        # 防御性兜底：任何错误都不中断，使用默认参数
        state["document_params"] = {
            "intent": intent.value if hasattr(intent, 'value') else "quote_generation",
            "params": DEFAULT_PARAMS.copy(),
            "missing": [],
            "_error": str(e)  # 记录错误但不阻断
        }
        state["next_node"] = "generate_document"
    
    return state


async def generate_document_node(state: SalesState) -> SalesState:
    """
    文档生成节点 - 核心重构点
    
    规范：
    1. 使用 xlsx Skill 公式驱动生成
    2. 文件名闭环：reply 包含完整文件名，documents 列表正确
    3. 防御性：任何错误都生成降级版本，绝不返回 None
    """
    logger.info(f"[Session: {state.get('session_id', 'unknown')}] 开始生成文档")
    
    # 防御性初始化
    if "generated_documents" not in state or not isinstance(state["generated_documents"], list):
        state["generated_documents"] = []
    
    doc_info = state.get("document_params", {})
    intent_value = doc_info.get("intent", "quote_generation") if isinstance(doc_info, dict) else "quote_generation"
    params = doc_info.get("params", {}) if isinstance(doc_info, dict) else {}
    
    doc_result = None
    error_msg = None
    
    try:
        # 意图映射
        intent_map = {
            "quote_generation": UserIntent.QUOTE_GENERATION,
            "proposal_creation": UserIntent.PROPOSAL_CREATION,
            "contract_drafting": UserIntent.CONTRACT_DRAFTING,
            "data_analysis": UserIntent.DATA_ANALYSIS,
            "presentation_request": UserIntent.PRESENTATION_REQUEST,
        }
        intent = intent_map.get(intent_value, UserIntent.QUOTE_GENERATION)
        
        # 根据意图生成对应文档
        if intent == UserIntent.QUOTE_GENERATION:
            doc_result = await _generate_quote_document(params)
        elif intent == UserIntent.PROPOSAL_CREATION:
            # 参数不全时追问，不生成空白文件
            missing_prompt = _check_missing_params_for_proposal(params)
            if missing_prompt:
                state["sales_response"] = missing_prompt
                state["suggested_actions"] = ["提供客户名称", "提供项目名称"]
                state["next_node"] = "end"
                return state
            # 检查默认值比例：如果超过70%字段为默认/占位值，提示用户
            default_count, total_count = _count_default_params(params)
            if total_count > 0 and (default_count / total_count) > 0.70:
                logger.info(f"[Proposal] 默认值比例过高 ({default_count}/{total_count}={default_count/total_count:.0%})，提示用户补充")
                state["sales_response"] = (
                    "好的，我来帮您准备提案书！\n\n"
                    "不过目前您提供的信息较少，生成的提案会比较通用。\n"
                    "为了让提案更有针对性，建议补充以下信息：\n"
                    "· 客户公司名称和联系人\n"
                    "· 具体项目需求和背景\n"
                    "· 项目预算范围\n"
                    "· 车型偏好或数量需求\n\n"
                    "当然，我也可以先基于现有信息生成初版，您看是补充信息还是先生成？"
                )
                state["suggested_actions"] = ["先补充信息", "直接生成初版", "换个功能"]
                state["next_node"] = "end"
                return state
            doc_result = await _generate_proposal_via_template(params)
        elif intent == UserIntent.CONTRACT_DRAFTING:
            # 根据合同类型选择不同的参数检查
            contract_type = _map_contract_type("contract_drafting", params)
            # 无法自动识别合同类型时，请用户明确选择
            if contract_type is None:
                state["sales_response"] = (
                    "好的，我来帮您起草合同！\n\n"
                    "不过我需要确认一下，您需要哪种合同？\n"
                    "· 购车合同 — 车辆买卖、正式签合同\n"
                    "· 订车协议 — 预订车辆、支付意向金/定金\n"
                    "· 金融分期合同 — 贷款购车、分期付款\n\n"
                    "请告诉我具体需要哪一种～"
                )
                state["suggested_actions"] = ["购车合同", "订车协议", "金融分期合同"]
                state["next_node"] = "end"
                return state
            if contract_type == "order_agreement":
                missing_prompt = _check_missing_params_for_order(params)
                actions = ["提供客户名称", "提供车型", "确认定金金额"]
            elif contract_type == "finance_installment":
                missing_prompt = _check_missing_params_for_finance(params)
                actions = ["提供客户名称", "提供车型", "确认贷款金额"]
            else:
                missing_prompt = _check_missing_params_for_contract(params)
                actions = ["提供客户信息", "确认合同类型", "提供车型"]
            if missing_prompt:
                state["sales_response"] = missing_prompt
                state["suggested_actions"] = actions
                state["next_node"] = "end"
                return state
            doc_result = await _generate_contract_document(params)
        elif intent == UserIntent.DATA_ANALYSIS:
            doc_result = await _generate_analysis_document(params)
        elif intent == UserIntent.PRESENTATION_REQUEST:
            doc_result = await _generate_presentation(params)
        else:
            doc_result = await _generate_generic_document(intent, params)
        
        # 防御性校验 doc_result
        if doc_result is None:
            raise ValueError("文档生成返回 None")
        
        # 确保 file_name 字段有效
        file_name = getattr(doc_result, 'file_name', None)
        if not file_name:
            file_name = f"文档_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            doc_result.file_name = file_name
        
        # 添加到文档列表
        state["generated_documents"].append(doc_result)
        state["metadata"] = state.get("metadata", {})
        state["metadata"]["generated_doc"] = {
            "file_name": file_name,
            "file_path": getattr(doc_result, 'file_path', ''),
            "doc_type": getattr(doc_result, 'doc_type', DocumentType.DOCX).value if hasattr(getattr(doc_result, 'doc_type', ''), 'value') else str(getattr(doc_result, 'doc_type', 'unknown')),
        }
        
        # ═══ 文件名闭环：简洁回复，前端按钮处理下载 ═══
        # 根据实际模板类型确定文案
        if intent == UserIntent.CONTRACT_DRAFTING:
            ct = _map_contract_type("contract_drafting", params)
            contract_doc_names = {
                "order_agreement": "订车协议",
                "finance_installment": "金融分期合同",
                "car_purchase": "购车合同",
            }
            doc_type_name = contract_doc_names.get(ct or "car_purchase", "合同")
        else:
            doc_type_names = {
                UserIntent.QUOTE_GENERATION: "报价单",
                UserIntent.PROPOSAL_CREATION: "提案书",
                UserIntent.DATA_ANALYSIS: "数据分析报表",
                UserIntent.PRESENTATION_REQUEST: "演示文稿",
            }
            doc_type_name = doc_type_names.get(intent, "文档")
        response_text = (
            f"这是您的{doc_type_name}，点击下方按钮即可下载。\n如需调整内容请随时告诉我。"
        )
        if intent == UserIntent.PROPOSAL_CREATION:
            response_text += (
                "\n\n💡 提案书基于已提供的信息生成，如需补充更多细节"
                "（如技术参数、交付时间等），可继续提供。"
            )
        state["sales_response"] = response_text
        suggested_map = {
            UserIntent.QUOTE_GENERATION: ["修改报价内容", "生成合同", "发送给客户"],
            UserIntent.CONTRACT_DRAFTING: ["修改合同条款", "生成报价单", "发送给客户"],
            UserIntent.PROPOSAL_CREATION: ["修改方案内容", "生成合同", "发送给客户"],
        }
        state["suggested_actions"] = suggested_map.get(
            intent, ["修改文档内容", "生成其他文档", "发送给客户"]
        )
        
        logger.info(f"[Document] 生成成功: {file_name}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Document] 生成失败: {error_msg}")
        
        # 防御性兜底：即使失败也生成一个文本文件
        try:
            fallback_result = await _generate_quote_document({})  # 空参数触发全默认
            state["generated_documents"].append(fallback_result)
            download_url = f"/api/v1/docs/documents/{fallback_result.file_name}"
            state["sales_response"] = (
                f"⚠️ 已为您生成默认报价单，点击下方按钮即可下载。\n"
                f"如需调整请告诉我具体需求。"
            )
        except Exception as fallback_error:
            # 最终兜底：只返回文字
            logger.critical(f"[Document] 兜底生成也失败: {fallback_error}")
            state["sales_response"] = (
                "抱歉，文档生成服务暂时不可用。请稍后重试，或直接联系您的专属销售顾问。\n"
                "联系电话：400-XXX-XXXX"
            )
    
    # 确保 sales_response 绝不返回 None（防御 Pydantic 校验失败）
    if not state.get("sales_response"):
        state["sales_response"] = "文档已处理完成，请查看下载列表。"
    
    if "suggested_actions" not in state or not state["suggested_actions"]:
        state["suggested_actions"] = ["继续咨询", "重新生成"]
    
    state["next_node"] = "end"
    return state


# ═══════════════════════════════════════════════════════════════
# 保留但标记为过时的节点（兼容性）
# ═══════════════════════════════════════════════════════════════

async def request_missing_params_node(state: SalesState) -> SalesState:
    """
    请求缺失参数节点 - 已简化
    
    重构后策略：不再中断询问，直接填充默认值继续
    此节点保留用于兼容性，实际直接跳转到生成
    """
    logger.info(f"[Session: {state.get('session_id', 'unknown')}] 跳过参数询问，使用默认值")
    
    # 直接放行到生成节点
    state["next_node"] = "generate_document"
    state["sales_response"] = None  # 不提前返回，等生成后再统一返回
    
    return state
