"""
生成专业汽车金融分期付款合同模板 docx

参照银行标准汽车消费借款合同（18条），包含：
- LPR利率浮动机制
- 保险受益权（第一受益人）
- 不可撤销扣款授权
- 加速到期条款（11种违约情形）
- 罚息/复利计算
- 送达地址条款（含电子送达）
- 分期还款计划表

用法:
    cd backend && python scripts/build_finance_installment_template.py
"""

import os
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

# ═══════════════════════════════════════════════════════════════
# 样式工具函数
# ═══════════════════════════════════════════════════════════════
FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_BOLD_LABEL = "黑体", "黑体", "宋体", "黑体"
SIZE_TITLE, SIZE_HEADING, SIZE_BODY, SIZE_SMALL = Pt(18), Pt(12), Pt(10.5), Pt(9)

def set_font(run, name=FONT_BODY, size=SIZE_BODY, bold=False, color=None):
    run.font.name = name; run.font.size = size; run.bold = bold
    if color: run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="{name}"/>'); rPr.insert(0, rFonts)
    else: rFonts.set(qn('w:eastAsia'), name)

def add_paragraph(doc, text, font=FONT_BODY, size=SIZE_BODY, bold=False, alignment=None, space_after=Pt(6), space_before=Pt(0), indent=None):
    p = doc.add_paragraph()
    if alignment is not None: p.alignment = alignment
    pf = p.paragraph_format; pf.space_after = space_after; pf.space_before = space_before
    if indent is not None: pf.first_line_indent = indent
    run = p.add_run(text); set_font(run, font, size, bold)
    return p

def add_clause_heading(doc, number, title):
    p = doc.add_paragraph(); pf = p.paragraph_format; pf.space_before = Pt(12); pf.space_after = Pt(6)
    run = p.add_run(f"第{number}条  {title}"); set_font(run, FONT_HEADING, SIZE_HEADING, bold=True)
    return p

def add_placeholder_para(doc, label, placeholder, indent=Cm(0.74)):
    p = doc.add_paragraph(); pf = p.paragraph_format; pf.space_after = Pt(2)
    if indent: pf.left_indent = indent
    r1 = p.add_run(label); set_font(r1, FONT_BOLD_LABEL, SIZE_BODY, bold=True)
    r2 = p.add_run(f"{{{{{placeholder}}}}}"); set_font(r2, FONT_BODY, SIZE_BODY)
    return p

def add_body_para(doc, text, indent=Cm(0.74)):
    return add_paragraph(doc, text, FONT_BODY, SIZE_BODY, indent=indent, space_after=Pt(4))

def set_table_borders(table):
    tbl = table._tbl; tblPr = tbl.tblPr if tbl.tblPr is not None else parse_xml(f'<w:tblPr {nsdecls("w")}/>')
    borders = parse_xml(f'<w:tblBorders {nsdecls("w")}><w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/></w:tblBorders>')
    tblPr.append(borders)

OUTPUT_PATH = "data/templates/contracts/finance_installment.docx"


def build_template():
    doc = Document()

    section = doc.sections[0]
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.17)
    section.right_margin = Cm(3.17)

    # ─── 标题 ───
    add_paragraph(doc, "汽 车 金 融 分 期 付 款 合 同", FONT_TITLE, SIZE_TITLE, bold=True,
                  alignment=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(8))
    add_paragraph(doc, "（银行贷款标准版）", FONT_BODY, SIZE_SMALL,
                  alignment=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(16))
    add_placeholder_para(doc, "合同编号：", "contract_no", indent=None)
    add_paragraph(doc, "", space_after=Pt(4))

    # 签约声明
    add_body_para(doc, "本合同各方基于平等、自愿、诚实信用原则，经协商一致，依法签订本合同。各方承诺恪守合同约定，严格履行合同义务。")
    add_paragraph(doc, "", space_after=Pt(8))

    # ═══════════════════════════════════════
    # 第一条 合同当事人
    # ═══════════════════════════════════════
    add_clause_heading(doc, "一", "合同当事人")
    add_body_para(doc, "（一）贷款人（甲方）：")
    add_placeholder_para(doc, "名称：", "finance_company")
    add_placeholder_para(doc, "统一社会信用代码：", "finance_credit_code")
    add_placeholder_para(doc, "地址：", "finance_address")
    add_placeholder_para(doc, "贷款业务联系电话：", "finance_phone")
    add_paragraph(doc, "", space_after=Pt(4))
    add_body_para(doc, "（二）借款人（乙方）：")
    add_placeholder_para(doc, "姓名：", "borrower_name")
    add_placeholder_para(doc, "身份证号/统一社会信用代码：", "borrower_id_card")
    add_placeholder_para(doc, "住所（地址）：", "borrower_address")
    add_placeholder_para(doc, "联系电话：", "borrower_phone")
    add_placeholder_para(doc, "还款账户开户行：", "borrower_bank")
    add_placeholder_para(doc, "还款账号：", "borrower_account")
    add_paragraph(doc, "", space_after=Pt(4))
    add_body_para(doc, "（三）保证人（丙方，如有）：")
    add_placeholder_para(doc, "姓名/名称：", "guarantor_name")
    add_placeholder_para(doc, "身份证号/统一社会信用代码：", "guarantor_id_card")
    add_placeholder_para(doc, "联系电话：", "guarantor_phone")

    # ═══════════════════════════════════════
    # 第二条 贷款金额与用途
    # ═══════════════════════════════════════
    add_clause_heading(doc, "二", "贷款金额与用途")
    add_body_para(doc, f"1. 本合同项下贷款金额为人民币（大写）{{{{loan_amount_cn}}}}元整（小写¥{{{{loan_amount}}}}元）。")
    add_body_para(doc, "2. 贷款专项用于乙方购买以下车辆：")
    # 车辆信息小表
    t = doc.add_table(rows=1, cols=2); t.alignment = WD_TABLE_ALIGNMENT.CENTER; set_table_borders(t)
    for i, txt in enumerate(["项  目", "内  容"]):
        c = t.rows[0].cells[i]; c.text = ""
        r = c.paragraphs[0].add_run(txt); set_font(r, FONT_BOLD_LABEL, SIZE_SMALL, bold=True)
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for label, ph in [("车辆品牌型号","car_brand {{car_model}}"), ("车身颜色","car_color"),
                       ("车架号（VIN）","vin"), ("发动机号","engine_no"),
                       ("车辆总价（元）","total_price")]:
        row = t.add_row()
        for j, text in enumerate([label, f"{{{{{ph}}}}}" if "{{" not in ph else ph]):
            c = row.cells[j]; c.text = ""
            rn = c.paragraphs[0].add_run(text)
            set_font(rn, FONT_BOLD_LABEL if j==0 else FONT_BODY, SIZE_SMALL, bold=(j==0))
    add_body_para(doc, "3. 未经甲方书面同意，乙方不得改变贷款用途。")

    # ═══════════════════════════════════════
    # 第三条 贷款期限
    # ═══════════════════════════════════════
    add_clause_heading(doc, "三", "贷款期限")
    add_body_para(doc, "1. 贷款期限为 {{installments}} 期（月），自甲方首次放款之日起算。")
    add_body_para(doc, "2. 首次还款日为 {{first_repayment_date}}，其后每月 {{repayment_day}} 日为还款日。最后一期还款日为 {{last_repayment_date}}。")

    # ═══════════════════════════════════════
    # 第四条 贷款利率（LPR浮动机制）
    # ═══════════════════════════════════════
    add_clause_heading(doc, "四", "贷款利率")
    add_body_para(doc, "1. 本合同项下贷款利率按以下方式确定：以全国银行间同业拆借中心公布的 {{lpr_term}} 贷款市场报价利率（LPR）为基准利率，")
    add_body_para(doc, f"   □ 加 {{lpr_spread_bp}} 个基点（BP）")
    add_body_para(doc, f"   □ 减 {{lpr_spread_bp}} 个基点（BP）")
    add_body_para(doc, "   当前执行年利率为 {{annual_rate}}%。")
    add_body_para(doc, "2. 如遇 LPR 调整，本合同利率自调整日的次年1月1日起相应调整。甲方不另行通知，乙方确认知晓。")
    add_body_para(doc, "3. 本合同贷款利率为浮动利率，乙方不得要求转为固定利率。")

    # ═══════════════════════════════════════
    # 第五条 首付与放款
    # ═══════════════════════════════════════
    add_clause_heading(doc, "五", "首付与放款条件")
    add_body_para(doc, "1. 乙方应自筹首付款人民币 {{down_payment}} 元（大写：{{down_payment_cn}}元整），于放款前支付给车辆经销商。")
    add_body_para(doc, "2. 贷款金额由甲方直接划付至以下经销商账户：")
    add_placeholder_para(doc, "经销商名称：", "dealer_name")
    add_placeholder_para(doc, "经销商账号：", "dealer_account")
    add_body_para(doc, "3. 甲方放款须满足以下全部条件：")
    add_body_para(doc, "   (1) 借款凭证（借据）已经乙方签字确认；")
    add_body_para(doc, "   (2) 车辆抵押登记手续已办妥且无瑕疵；")
    add_body_para(doc, "   (3) 保险合同已将甲方列为第一受益人；")
    add_body_para(doc, "   (4) 乙方已支付首付款并提供付款凭证。")

    # ═══════════════════════════════════════
    # 第六条 还款方式
    # ═══════════════════════════════════════
    add_clause_heading(doc, "六", "还款方式")
    add_body_para(doc, "1. 还款方式为：□ 等额本息  □ 等额本金  □ 其他：{{repayment_method_other}}")
    add_body_para(doc, "2. 月还款金额约为人民币 {{monthly_payment}} 元（以实际还款计划表为准）。")
    add_body_para(doc, "3. 乙方应在每月还款日 {{repayment_day}} 日16:00前将足额还款资金存入还款账户。")

    # ═══════════════════════════════════════
    # 第七条 不可撤销扣款授权
    # ═══════════════════════════════════════
    add_clause_heading(doc, "七", "不可撤销扣款授权")
    add_body_para(doc, "1. 乙方不可撤销地授权甲方从本合同约定的还款账户中直接扣收每期应还本金、利息、罚息、复利及其他应由乙方承担的费用。")
    add_body_para(doc, "2. 如还款账户余额不足，甲方有权多次扣收，直至本息全部清偿。")
    add_body_para(doc, "3. 乙方变更还款账户的，应提前 10 个工作日书面通知甲方并重新签署授权书。变更前原账户仍为有效扣款账户。")

    # ═══════════════════════════════════════
    # 第八条 提前还款
    # ═══════════════════════════════════════
    add_clause_heading(doc, "八", "提前还款")
    add_body_para(doc, "1. 贷款发放满 {{early_repay_lock_months}} 个月后，乙方可申请提前归还全部或部分贷款本金。")
    add_body_para(doc, "2. 提前还款手续费为提前还款金额的 {{early_repay_fee_rate}}%，最低 {{early_repay_fee_min}} 元。")
    add_body_para(doc, "3. 部分提前还款后，剩余贷款本金可选择：□ 缩短期限，月供不变  □ 期限不变，月供减少。")

    # ═══════════════════════════════════════
    # 第九条 保险
    # ═══════════════════════════════════════
    add_clause_heading(doc, "九", "保险条款")
    add_body_para(doc, "1. 在贷款全部清偿前，乙方应按年投保以下保险，保险期限不得中断：")
    add_body_para(doc, "   (1) 机动车交通事故责任强制保险（交强险）；")
    add_body_para(doc, "   (2) 机动车综合商业保险（不低于：车损险、三者险 {{insurance_third_party}} 万、不计免赔）。")
    add_body_para(doc, "2. 保险合同中应明确载明：甲方为商业车损险的第一受益人。")
    add_body_para(doc, "3. 乙方应于保险到期前 15 日内续保并提供保险单复印件给甲方。逾期未续保的，甲方有权代为投保，保费由乙方承担并按日万分之五计收资金占用费。")
    add_body_para(doc, "4. 保险事故发生后，乙方应立即通知甲方和保险公司。保险赔款优先用于清偿本合同项下的贷款本息，剩余部分归乙方。")

    # ═══════════════════════════════════════
    # 第十条 车辆抵押
    # ═══════════════════════════════════════
    add_clause_heading(doc, "十", "车辆抵押登记")
    add_body_para(doc, "1. 乙方将本合同项下所购车辆抵押给甲方，作为偿还全部贷款本息及相关费用的担保。")
    add_body_para(doc, "2. 抵押担保范围：本合同项下的贷款本金、利息、罚息、复利、违约金、损害赔偿金以及甲方为实现债权和抵押权而发生的全部费用（包括但不限于诉讼费/仲裁费、律师费、评估费、拍卖费、差旅费等）。")
    add_body_para(doc, "3. 双方应在提车后 30 日内到车辆登记地公安机关交通管理部门办妥抵押登记。抵押登记费用由乙方承担。")
    add_body_para(doc, "4. 在贷款全部清偿前，未经甲方书面同意，乙方不得转让、赠与或以其他方式处分抵押车辆。")
    add_body_para(doc, "5. 贷款本息全部清偿后，甲方应在 15 个工作日内配合乙方办理解除抵押登记手续。")

    # ═══════════════════════════════════════
    # 第十一条 加速到期条款
    # ═══════════════════════════════════════
    add_clause_heading(doc, "十一", "贷款加速到期条款")
    add_body_para(doc, "出现以下任一情形时，甲方有权宣布贷款立即到期，要求乙方立即清偿全部剩余贷款本息、罚息及其他应付费用：")
    add_body_para(doc, "   1. 乙方未按期足额偿还任意一期贷款本息；")
    add_body_para(doc, "   2. 乙方连续 {{default_months}} 期或累计 {{default_months_total}} 期未按时偿还贷款本息；")
    add_body_para(doc, "   3. 乙方提供虚假材料或做出虚假陈述；")
    add_body_para(doc, "   4. 乙方将贷款资金挪作他用；")
    add_body_para(doc, "   5. 未经甲方同意，乙方转让、赠与或以其他方式处分抵押车辆；")
    add_body_para(doc, "   6. 抵押车辆被查封、扣押、监管或被第三方主张权利；")
    add_body_para(doc, "   7. 乙方死亡、被宣告失踪或丧失民事行为能力且无继承人或监护人继续履行合同；")
    add_body_para(doc, "   8. 乙方涉及重大诉讼或仲裁，可能影响其偿还能力的；")
    add_body_para(doc, "   9. 抵押车辆价值明显减少（贬值超过30%），乙方不按要求提供补充担保的；")
    add_body_para(doc, "  10. 保险中断或保险受益人变更未获甲方同意的；")
    add_body_para(doc, "  11. 其他违反本合同约定，可能危及甲方债权的行为。")

    # ═══════════════════════════════════════
    # 第十二条 罚息与复利
    # ═══════════════════════════════════════
    add_clause_heading(doc, "十二", "罚息与复利")
    add_body_para(doc, "1. 乙方未按合同约定日期偿还贷款本金或利息的，自逾期之日起，甲方有权按以下标准计收罚息：")
    add_body_para(doc, f"   逾期罚息利率 = 本合同约定的贷款利率 × (1 + {{penalty_rate_multiplier}}%)")
    add_body_para(doc, "2. 对不能按期支付的利息，自逾期之日起按罚息利率计收复利，按月结息。")
    add_body_para(doc, "3. 逾期天数自约定还款日次日起计算至实际清偿日止。")

    # ═══════════════════════════════════════
    # 第十三条 费用承担
    # ═══════════════════════════════════════
    add_clause_heading(doc, "十三", "费用承担")
    add_body_para(doc, "以下费用由乙方承担：")
    add_body_para(doc, "   1. 办理车辆抵押登记、解除抵押登记的全部费用；")
    add_body_para(doc, "   2. 本合同项下的保险费（含甲方代为投保的费用）；")
    add_body_para(doc, "   3. 甲方为实现债权和抵押权而支付的全部费用（包括但不限于律师费、诉讼费、保全费、评估费、拍卖费、差旅费等）。")

    # ═══════════════════════════════════════
    # 第十四条 送达地址条款
    # ═══════════════════════════════════════
    add_clause_heading(doc, "十四", "送达地址条款")
    add_body_para(doc, "1. 本合同载明的各方地址为有效送达地址。一方变更地址的，应在变更后 5 日内书面通知其他方。未通知的，原地址仍视为有效。")
    add_body_para(doc, "2. 通过以下任一方式发送的通知均视为有效送达：")
    add_body_para(doc, "   (1) 挂号信或快递：投递后第 3 日视为送达；")
    add_body_para(doc, "   (2) 手机短信：发送之日视为送达；")
    add_body_para(doc, "   (3) 电子邮件：发送之日视为送达。")
    add_body_para(doc, "3. 因地址变更未及时通知导致的文书无法送达，由变更方承担全部法律后果。")

    # ═══════════════════════════════════════
    # 第十五条 违约责任
    # ═══════════════════════════════════════
    add_clause_heading(doc, "十五", "违约责任")
    add_body_para(doc, "1. 甲方未按合同约定发放贷款的，应向乙方支付未发放金额 {{lender_default_rate}}% 的违约金。")
    add_body_para(doc, "2. 因乙方原因导致贷款未能发放的，乙方应赔偿甲方因此遭受的直接经济损失。")
    add_body_para(doc, "3. 乙方违约的，除按本合同第十二条承担罚息外，还应赔偿甲方为实现债权而支出的合理费用。")

    # ═══════════════════════════════════════
    # 第十六条 争议解决
    # ═══════════════════════════════════════
    add_clause_heading(doc, "十六", "争议解决")
    add_body_para(doc, "因履行本合同发生争议的，双方应友好协商解决；协商不成的，选择以下方式之一解决（√选）：")
    add_body_para(doc, "   □ 向 {{arbitration_commission}} 申请仲裁。")
    add_body_para(doc, "   □ 向甲方所在地有管辖权的人民法院提起诉讼。")

    # ═══════════════════════════════════════
    # 第十七条 其他约定
    # ═══════════════════════════════════════
    add_clause_heading(doc, "十七", "其他约定")
    add_body_para(doc, "1. 本合同未尽事宜，可由各方签订补充协议，补充协议与本合同具有同等法律效力。")
    add_body_para(doc, "2. 本合同任何条款无效不影响其他条款的效力。")
    add_body_para(doc, "3. 甲方对知悉的乙方个人信息负有保密义务，未经乙方同意不得向第三方泄露，但依法向征信机构报送信用信息及为实现债权而披露的除外。")
    add_body_para(doc, "4. 乙方同意甲方将其信用信息（包括逾期信息）报送中国人民银行征信中心及其他依法设立的征信机构。")
    add_body_para(doc, "5. 本合同一式叁份，甲、乙、丙三方各执壹份，自各方签字或盖章之日起生效。")

    add_paragraph(doc, "", space_after=Pt(16))

    # ═══════════════════════════════════════
    # 签署栏（三栏）
    # ═══════════════════════════════════════
    sign_table = doc.add_table(rows=1, cols=3) if False else doc.add_table(rows=1, cols=2)
    sign_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(sign_table)
    sign_cols = [
        ("甲方：贷款人（盖章）", "{{finance_company}}\n\n法定代表人/授权代理人：___________\n\n日期：    年    月    日"),
        ("乙方：借款人（签字）", "{{borrower_name}}\n\n身份证号：{{borrower_id_card}}\n\n日期：    年    月    日"),
    ]
    # Create 2-column sign table
    sign_table = doc.add_table(rows=1, cols=2)
    sign_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(sign_table)
    for i, (title, content) in enumerate(sign_cols):
        cell = sign_table.rows[0].cells[i]; cell.text = ""
        p1 = cell.paragraphs[0]
        r1 = p1.add_run(title + "\n\n"); set_font(r1, FONT_BOLD_LABEL, SIZE_BODY, bold=True)
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2 = cell.add_paragraph()
        r2 = p2.add_run(content); set_font(r2, FONT_BODY, SIZE_SMALL)
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ─── 脚注 ───
    add_paragraph(doc, "", space_after=Pt(16))
    add_paragraph(doc, "（本合同依据《中华人民共和国民法典》及《商业银行法》《贷款通则》等法律法规制定。）",
                  FONT_BODY, Pt(8), alignment=WD_ALIGN_PARAGRAPH.CENTER)
    add_paragraph(doc, "（标注【需人工确认】的字段请签约前核对确认。）",
                  FONT_BODY, Pt(8), alignment=WD_ALIGN_PARAGRAPH.CENTER)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    doc.save(OUTPUT_PATH)
    print(f"OK: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_template()
