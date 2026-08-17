"""
模板服务 - 加载 docx 模板并自动填充字段

工作流程：
1. 从 data/templates/ 加载 docx 模板
2. 替换 {{field_name}} 占位符为实际值
3. 处理表格中的占位符
4. 保存填充后的文档到 output/

用法:
    from app.services.template_service import TemplateService
    svc = TemplateService()
    filepath = await svc.fill_contract("car_purchase", {"buyer_name": "张三", ...})
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

from docx import Document

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("template_service")

# 模板路径映射
TEMPLATE_MAP = {
    # 合同模板
    "car_purchase": "data/templates/contracts/car_purchase.docx",
    "order_agreement": "data/templates/contracts/order_agreement.docx",
    "finance_installment": "data/templates/contracts/finance_installment.docx",
    # 提案书模板
    "proposal": "data/templates/proposals/proposal.docx",
}


class TemplateService:
    """模板填充服务"""

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir

    def _get_template_path(self, template_key: str) -> str:
        """获取模板文件绝对路径"""
        relative = TEMPLATE_MAP.get(template_key)
        if not relative:
            raise ValueError(f"未知模板: {template_key}，可用模板: {list(TEMPLATE_MAP.keys())}")
        full_path = os.path.join(self.base_dir, relative)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"模板文件不存在: {full_path}")
        return full_path

    def _replace_in_paragraph(self, paragraph, data: Dict[str, Any]):
        """
        替换段落中的 {{key}} 占位符

        python-docx 的段落由多个 run 组成，占位符可能被拆分到不同 run 中。
        策略：先拼接全文本替换，再写回第一个 run，清空其余 run。
        """
        full_text = paragraph.text
        if "{{" not in full_text:
            return

        # 替换所有 {{key}} 占位符
        def replacer(match):
            key = match.group(1).strip()
            return str(data.get(key, match.group(0)))  # 未匹配的保留原样

        new_text = re.sub(r"\{\{(\w+)\}\}", replacer, full_text)

        if new_text == full_text:
            return

        # 写回：第一个 run 设置全文，其余 run 清空
        if paragraph.runs:
            paragraph.runs[0].text = new_text
            for run in paragraph.runs[1:]:
                run.text = ""

    def _replace_in_table(self, table, data: Dict[str, Any]):
        """替换表格中所有单元格的占位符"""
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    self._replace_in_paragraph(paragraph, data)

    async def fill_template(
        self,
        template_key: str,
        data: Dict[str, Any],
        output_filename: Optional[str] = None,
    ) -> str:
        """
        填充模板并保存

        Args:
            template_key: 模板标识（如 "car_purchase"）
            data: 填充数据字典，key 为占位符名称
            output_filename: 输出文件名（不含路径），默认自动生成

        Returns:
            生成文件的绝对路径
        """
        template_path = self._get_template_path(template_key)
        doc = Document(template_path)

        # 自动填充标准字段
        auto_fields = {
            "sign_date": datetime.now().strftime("%Y年%m月%d日"),
            "proposal_date": datetime.now().strftime("%Y年%m月%d日"),
            "contract_no": f"C{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "agreement_no": f"A{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "proposal_no": f"P{datetime.now().strftime('%Y%m%d%H%M%S')}",
        }
        merged_data = {**auto_fields, **data}

        # 替换段落中的占位符
        for paragraph in doc.paragraphs:
            self._replace_in_paragraph(paragraph, merged_data)

        # 替换表格中的占位符
        for table in doc.tables:
            self._replace_in_table(table, merged_data)

        # 生成输出路径
        output_dir = os.path.join(self.base_dir, settings.output_dir)
        os.makedirs(output_dir, exist_ok=True)

        if not output_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{template_key}_{timestamp}.docx"

        output_path = os.path.join(output_dir, output_filename)
        doc.save(output_path)

        logger.info(f"[Template] 模板填充完成: {template_key} -> {output_path}")
        return output_path

    async def fill_contract(self, contract_type: str, data: Dict[str, Any]) -> str:
        """
        填充合同模板（便捷方法）

        Args:
            contract_type: 合同类型 (car_purchase / order_agreement / finance_installment)
            data: 合同数据

        Returns:
            生成文件路径
        """
        return await self.fill_template(contract_type, data)

    async def fill_proposal(self, data: Dict[str, Any]) -> str:
        """
        填充提案书模板（便捷方法）

        Args:
            data: 提案书数据

        Returns:
            生成文件路径
        """
        return await self.fill_template("proposal", data)

    def list_templates(self) -> Dict[str, str]:
        """列出所有可用模板"""
        result = {}
        for key, relative in TEMPLATE_MAP.items():
            full_path = os.path.join(self.base_dir, relative)
            result[key] = "可用" if os.path.exists(full_path) else "缺失"
        return result
