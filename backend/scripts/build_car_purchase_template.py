"""
生成 GF-2015-0121 标准汽车购车合同模板 docx

国家市场监督管理总局《汽车买卖合同》示范文本 (GF-2015-0121)
依据《中华人民共和国民法典》《产品质量法》《消费者权益保护法》等

用法:
    cd backend && python scripts/build_car_purchase_template.py
"""

import os
from datetime import datetime
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

OUTPUT_PATH = "data/templates/contracts/car_purchase.docx"

# ═══════════════════════════════════════════════════════════════
# 样式定义
# ═══════════════════════════════════════════════════════════════

FONT_TITLE = "黑体"
FONT_HEADING = "黑体"
FONT_BODY = "宋体"
FONT_BOLD_LABEL = "黑体"

SIZE_TITLE = Pt(18)
SIZE_HEADING = Pt(12)
SIZE_BODY = Pt(10.5)
SIZE_SMALL = Pt(9)

def set_font(run, name=FONT_BODY, size=SIZE_BODY, bold=False, color=None):
    """统一字体设置，同时设置中文字体"""
    run.font.name = name
    run.font.size = size
    run.bold = bold
    if color:
        run.font.color.rgb = color
    # 设置中文字体 (eastAsia)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="{name}"/>')
        rPr.insert(0, rFonts)
    else:
        rFonts.set(qn('w:eastAsia'), name)

def add_paragraph(doc, text, font=FONT_BODY, size=SIZE_BODY, bold=False, alignment=None, space_after=Pt(6), space_before=Pt(0), indent=None):
    """添加格式化段落"""
    p = doc.add_paragraph()
    if alignment is not None:
        p.alignment = alignment
    pf = p.paragraph_format
    pf.space_after = space_after
    pf.space_before = space_before
    if indent is not None:
        pf.first_line_indent = indent
    run = p.add_run(text)
    set_font(run, font, size, bold)
    return p

def add_clause_heading(doc, number, title):
    """添加条款标题：第X条 标题"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(12)
    pf.space_after = Pt(6)
    run = p.add_run(f"第{number}条  {title}")
    set_font(run, FONT_HEADING, SIZE_HEADING, bold=True)
    return p

def add_placeholder_para(doc, label, placeholder, indent=Cm(0.74)):
    """添加带占位符的标签行：标签：{{placeholder}}"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(2)
    if indent:
        pf.left_indent = indent
    run1 = p.add_run(label)
    set_font(run1, FONT_BOLD_LABEL, SIZE_BODY, bold=True)
    run2 = p.add_run(f"{{{{{placeholder}}}}}")
    set_font(run2, FONT_BODY, SIZE_BODY)
    return p

def add_body_para(doc, text, indent=Cm(0.74)):
    """添加正文段落"""
    return add_paragraph(doc, text, FONT_BODY, SIZE_BODY, indent=indent, space_after=Pt(4))

def add_table_row(table, cells_data, header=False):
    """添加表格行"""
    row = table.add_row()
    for i, (text, width_ratio) in enumerate(cells_data):
        cell = row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(text)
        set_font(run, FONT_BOLD_LABEL if header else FONT_BODY, SIZE_SMALL, bold=header)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if header else WD_ALIGN_PARAGRAPH.LEFT
        # 设置单元格边框
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        tcBorders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            '<w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            '<w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            '<w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            '</w:tcBorders>'
        )
        tcPr.append(tcBorders)

def set_table_borders(table):
    """给整个表格设置边框"""
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else parse_xml(f'<w:tblPr {nsdecls("w")}/>')
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '</w:tblBorders>'
    )
    tblPr.append(borders)


def build_template():
    doc = Document()

    # ─── 页面设置 ───
    section = doc.sections[0]
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.17)
    section.right_margin = Cm(3.17)

    # ─── 合同标题 ───
    add_paragraph(doc, "汽 车 买 卖 合 同", FONT_TITLE, SIZE_TITLE, bold=True,
                  alignment=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(8))
    add_paragraph(doc, "（GF-2015-0121 示范文本）", FONT_BODY, SIZE_SMALL,
                  alignment=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(16))

    # ─── 合同编号 ───
    add_placeholder_para(doc, "合同编号：", "contract_no", indent=None)
    add_paragraph(doc, "", space_after=Pt(8))

    # ═════════════════════════════════════════════════════════
    # 甲乙双方信息
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "一、", "合同当事人")
    add_placeholder_para(doc, "甲方（卖方）：", "seller_name")
    add_placeholder_para(doc, "统一社会信用代码：", "seller_credit_code")
    add_placeholder_para(doc, "地址：", "seller_address")
    add_placeholder_para(doc, "法定代表人：", "seller_representative")
    add_placeholder_para(doc, "联系电话：", "seller_phone")
    add_paragraph(doc, "", space_after=Pt(4))
    add_placeholder_para(doc, "乙方（买方）：", "buyer_name")
    add_placeholder_para(doc, "身份证号／统一社会信用代码：", "buyer_id_card")
    add_placeholder_para(doc, "住所（地址）：", "buyer_address")
    add_placeholder_para(doc, "联系电话：", "buyer_phone")
    add_placeholder_para(doc, "邮政编码：", "buyer_zip")

    # ═════════════════════════════════════════════════════════
    # 第一条 车辆信息
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "一", "标的物 — 车辆信息")
    add_body_para(doc, "甲方出售的车辆应为经国家有关部门公布、备案的汽车产品公告上的产品或合法进口产品，并符合以下要求：")

    # 车辆信息表格
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table)
    # 表头
    hdr_cells = table.rows[0].cells
    for i, text in enumerate(["项  目", "内  容"]):
        hdr_cells[i].text = ""
        p = hdr_cells[i].paragraphs[0]
        run = p.add_run(text)
        set_font(run, FONT_BOLD_LABEL, SIZE_SMALL, bold=True)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    vehicle_fields = [
        ("汽车品牌", "car_brand"),
        ("型号规格", "car_model"),
        ("生产国别／产地", "car_origin"),
        ("生产厂名称", "manufacturer"),
        ("车身颜色", "car_color"),
        ("内饰颜色", "interior_color"),
        ("排量／发动机类型", "displacement"),
        ("主要配置", "car_config"),
        ("车架号（VIN）", "vin"),
        ("发动机号", "engine_no"),
        ("生产日期", "production_date"),
        ("合格证编号", "certificate_no"),
    ]
    for label, placeholder in vehicle_fields:
        row = table.add_row()
        # 左：标签
        c0 = row.cells[0]
        c0.text = ""
        p0 = c0.paragraphs[0]
        r0 = p0.add_run(label)
        set_font(r0, FONT_BOLD_LABEL, SIZE_SMALL, bold=True)
        pf = p0.paragraph_format
        pf.space_before = Pt(1)
        pf.space_after = Pt(1)
        # 右：占位符
        c1 = row.cells[1]
        c1.text = ""
        p1 = c1.paragraphs[0]
        r1 = p1.add_run(f"{{{{{placeholder}}}}}")
        set_font(r1, FONT_BODY, SIZE_SMALL)
        pf2 = p1.paragraph_format
        pf2.space_before = Pt(1)
        pf2.space_after = Pt(1)

    add_paragraph(doc, "", space_after=Pt(8))

    # ═════════════════════════════════════════════════════════
    # 第二条 数量与价款
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "二", "数量与价款")
    add_body_para(doc, "1. 车辆数量：壹（1）台。")
    add_placeholder_para(doc, "2. 车辆单价（人民币）：", "car_price", indent=Cm(0.74))
    add_body_para(doc, "3. 车辆总价款（不含税）：人民币（大写）{{total_price_cn}}元整（小写¥{{car_price}}元）。")

    # ═════════════════════════════════════════════════════════
    # 第三条 付款方式
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "三", "付款方式")
    add_body_para(doc, "双方约定采用以下第 {{payment_mode}} 种方式付款：")
    add_body_para(doc, "□ 方式一：直接付款。乙方于本合同签订之日起 {{payment_days}} 日内，一次性向甲方付清全部车款。")
    add_body_para(doc, "□ 方式二：汽车消费贷款。")
    add_body_para(doc, f"    首付比例：{{{{down_payment_ratio}}}}%，首付金额人民币{{{{down_payment}}}}元，于本合同签订之日起3日内支付。")
    add_body_para(doc, f"    余款人民币{{{{loan_amount}}}}元，由乙方通过金融机构办理汽车消费贷款支付。双方另行签署《贷款购车事项委托协议》。")
    add_body_para(doc, "□ 方式三：其他付款方式。{{other_payment_terms}}")
    add_placeholder_para(doc, "付款方式说明：", "payment_method", indent=Cm(0.74))

    # ═════════════════════════════════════════════════════════
    # 第四条 质量标准
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "四", "质量标准")
    add_body_para(doc, "1. 甲方出售的车辆，质量应符合国家关于汽车产品的强制性标准或行业标准，没有强制性标准和行业标准的，应符合保障人体健康和人身、财产安全的要求，并达到产品说明书载明的技术指标。")
    add_body_para(doc, "2. 甲方出售的车辆必须是经国家有关部门公布、备案的汽车产品公告上的产品或合法进口产品，且符合生产厂出厂检验标准。")
    add_body_para(doc, "3. 甲方在车辆交付前应完成 PDI（Pre-Delivery Inspection，交车前检查）检测，并排除已发现的故障或瑕疵。乙方有权查阅 PDI 检测报告。")
    add_body_para(doc, "4. 甲方应当向乙方明示所售车辆是否为事故车、泡水车、火烧车、质损车、召回车、三包退换车等特殊情形，如有上述情形应书面详细告知。")

    # ═════════════════════════════════════════════════════════
    # 第五条 交付与验收
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "五", "交付与验收")
    add_placeholder_para(doc, "1. 交车时间：", "delivery_date")
    add_placeholder_para(doc, "2. 交车地点：", "delivery_location")
    add_body_para(doc, "3. 提车方式：□ 乙方自提  □ 甲方送车上门  □ 委托运输方代提")
    add_body_para(doc, "4. 交车时里程表记录应小于 {{mileage_limit}} 公里（不含上牌服务里程）。")
    add_body_para(doc, "5. 甲方交车时应同时提供以下随车文件及物品：")
    add_body_para(doc, "   (1) 销售发票")
    add_body_para(doc, "   (2) 车辆合格证（国产车）／海关进口证明和商品检验单（进口车）")
    add_body_para(doc, "   (3) 三包凭证（家用汽车产品修理更换退货责任凭证）")
    add_body_para(doc, "   (4) 车辆使用说明书及维修保养手册")
    add_body_para(doc, "   (5) 随车工具、备胎、千斤顶、警示牌等附件清单")
    add_body_para(doc, "   (6) 其他：{{other_delivery_items}}")
    add_body_para(doc, "6. 乙方应在交车时当场对车辆外观、内饰、配置、随车物件和使用功能等进行认真检查确认。如有异议应当场向甲方提出，由双方协商处理。")
    add_body_para(doc, "7. 双方确认对所购车辆无异议后，应当签署《商品车辆交接书》。签署交接书后，车辆即视为正式交付，毁损、灭失的风险随之转移至乙方。")

    # ═════════════════════════════════════════════════════════
    # 第六条 三包条款（修理/更换/退货）
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "六", "关于修理、更换、退货的约定（三包条款）")
    add_body_para(doc, "依据《家用汽车产品修理更换退货责任规定》，双方约定如下：")
    add_body_para(doc, "1. 包修期：自开具购车发票之日起 {{warranty_years}} 年或行驶里程 {{warranty_km}} 万公里（以先到者为准）。在包修期内，因车辆质量问题导致的故障，甲方应当免费修理。")
    add_body_para(doc, "2. 三包有效期：自开具购车发票之日起 {{sanbao_years}} 年或行驶里程 {{sanbao_km}} 万公里（以先到者为准）。在三包有效期内，符合规定条件的，乙方享有修理、更换、退货的权利。")
    add_body_para(doc, "3. 退换车条件（符合其一即可）：")
    add_body_para(doc, "   (1) 同一故障经修理超过 5 次仍不能正常使用的；")
    add_body_para(doc, "   (2) 因质量问题累计修理时间超过 35 日的；")
    add_body_para(doc, "   (3) 发动机、变速器的主要零件经 2 次修理仍不能正常使用的；")
    add_body_para(doc, "   (4) 转向系统、制动系统、悬架系统、前/后桥、车身等因严重安全性能故障经 2 次修理仍未排除的。")
    add_body_para(doc, "4. 属于缺陷汽车产品召回范围的，甲方应当依法召回。乙方应当配合甲方完成召回程序。")
    add_body_para(doc, "5. 以下情形不适用三包：")
    add_body_para(doc, "   (1) 未按使用说明书正确使用、维护、修理车辆造成的故障；")
    add_body_para(doc, "   (2) 乙方自行改装、调整、拆卸车辆造成的故障；")
    add_body_para(doc, "   (3) 使用不符合质量标准的燃油、润滑油、冷却液等造成的故障。")

    # ═════════════════════════════════════════════════════════
    # 第七条 违约责任
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "七", "违约责任")
    add_body_para(doc, "（一）甲方违约责任：")
    add_body_para(doc, "1. 甲方未按时交付车辆的，自延期之日起至实际交付日止，每日按乙方已支付价款的 {{late_delivery_penalty_rate}}% 向乙方支付违约金。违约金最高不超过合同总价款的 {{penalty_cap}}%。")
    add_body_para(doc, "2. 甲方交付的车辆不符合本合同约定的质量标准的，乙方有权要求甲方更换符合质量标准的车辆。如无法更换的，乙方有权解除合同，甲方应返还全部已付款项，并向乙方支付合同总价款 {{penalty_cap}}% 的违约金。")
    add_body_para(doc, "3. 甲方存在欺诈行为（如故意隐瞒事故车、泡水车等），乙方有权依据《中华人民共和国消费者权益保护法》要求退一赔三。")
    add_paragraph(doc, "", space_after=Pt(4))
    add_body_para(doc, "（二）乙方违约责任：")
    add_body_para(doc, "1. 乙方未按时支付价款的，自延期之日起至实际支付日止，每日按逾期应付款的 {{late_payment_penalty_rate}}% 向甲方支付违约金。违约金最高不超过逾期应付款的 {{penalty_cap}}%。")
    add_body_para(doc, "2. 乙方不按时验收接车，且经甲方通知后超过 1 个月仍不验收的，甲方有权解除合同，已收取的定金不予退还。")
    add_paragraph(doc, "", space_after=Pt(4))
    add_body_para(doc, "（三）不可抗力：")
    add_body_para(doc, "因不可抗力不能履行本合同的，根据不可抗力的影响，部分或全部免除责任，但法律另有规定的除外。当事人迟延履行后发生不可抗力的，不能免除责任。")

    # ═════════════════════════════════════════════════════════
    # 第八条 定金条款
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "八", "定金条款")
    add_body_para(doc, "1. 本合同签订时，乙方应向甲方支付定金人民币 {{deposit_amount}} 元（大写：{{deposit_amount_cn}}元整）。定金不得超过合同总价款的 20%。")
    add_body_para(doc, "2. 本合同履行后，定金抵作价款。")
    add_body_para(doc, "3. 甲方违约导致合同解除的，应当双倍返还定金；乙方违约导致合同解除的，已收取的定金不予退还。")
    add_body_para(doc, '4. 双方明确约定：本条款中的“定金”为《民法典》第五百八十七条规定的违约定金，非“订金”或预付款。')

    # ═════════════════════════════════════════════════════════
    # 第九条 争议解决
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "九", "解决争议的方法")
    add_body_para(doc, "双方因履行本合同发生争议的，按以下顺序解决：")
    add_body_para(doc, "1. 友好协商；")
    add_body_para(doc, "2. 请求消费者协会或其他依法成立的调解组织调解；")
    add_body_para(doc, "3. 协商、调解不成的，选择以下方式之一解决（√选）：")
    add_body_para(doc, "   □ 向 {{arbitration_commission}} 申请仲裁。")
    add_body_para(doc, "   □ 向车辆销售方所在地有管辖权的人民法院提起诉讼。")

    # ═════════════════════════════════════════════════════════
    # 第十条 其他约定
    # ═════════════════════════════════════════════════════════
    add_clause_heading(doc, "十", "其他约定")
    add_body_para(doc, "1. 本合同未尽事宜，双方可另行签订补充协议。补充协议与本合同具有同等法律效力。")
    add_body_para(doc, "2. 本合同内容如有修改或补充，应当采用书面形式，经双方签字或盖章后生效。手写内容优于打印内容，大写数字优于阿拉伯数字。")
    add_body_para(doc, "3. 甲方对知悉的乙方个人信息负有保密义务，未经乙方同意不得向第三方泄露，法律另有规定的除外。乙方有权选择是否接受甲方的商业信息推送。")
    add_body_para(doc, "4. 本合同的附件包括：《商品车辆交接书》、销售发票、车辆合格证、三包凭证、使用说明书等，均为本合同不可分割的组成部分。")
    add_body_para(doc, "5. 本合同一式叁份，甲方执贰份，乙方执壹份，自双方签字或盖章之日起生效，具有同等法律效力。")

    add_paragraph(doc, "", space_after=Pt(16))

    # ═════════════════════════════════════════════════════════
    # 签署栏
    # ═════════════════════════════════════════════════════════
    sign_table = doc.add_table(rows=1, cols=2)
    sign_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(sign_table)
    for i, (party, ident) in enumerate([
        ("甲 方（卖方盖章）", "{{seller_name}}"),
        ("乙 方（买方签字）", "{{buyer_name}}"),
    ]):
        cell = sign_table.rows[0].cells[i]
        cell.text = ""
        p1 = cell.paragraphs[0]
        r1 = p1.add_run(f"{party}\n\n\n")
        set_font(r1, FONT_BOLD_LABEL, SIZE_BODY, bold=True)
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2 = cell.add_paragraph()
        r2 = p2.add_run("法定代表人／授权代理人：___________")
        set_font(r2, FONT_BODY, SIZE_SMALL)
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p3 = cell.add_paragraph()
        r3 = p3.add_run(f"签署日期：           年     月     日")
        set_font(r3, FONT_BODY, SIZE_SMALL)
        p3.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ─── 页脚说明 ───
    add_paragraph(doc, "", space_after=Pt(24))
    add_paragraph(doc, "（注：本合同依据国家市场监督管理总局《汽车买卖合同》示范文本 GF-2015-0121 制定。）",
                  FONT_BODY, SIZE_SMALL, alignment=WD_ALIGN_PARAGRAPH.CENTER)
    add_paragraph(doc, "（本合同条款中 【XXX】 为待填充字段，由 AI 销售顾问根据对话内容自动填写，未填充字段请手动补全。标注【需人工确认】的字段请签约前确认。）",
                  FONT_BODY, Pt(8), alignment=WD_ALIGN_PARAGRAPH.CENTER)

    # ─── 保存 ───
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    doc.save(OUTPUT_PATH)
    print(f"✅ 购车合同模板已生成: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_template()
