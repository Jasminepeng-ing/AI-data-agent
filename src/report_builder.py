"""
src/report_builder.py
=====================
报告生成模块（纯 Python，不依赖 Streamlit）。

提供两种报告格式：
- Word (.docx): python-docx 格式化，适合二次编辑
- PDF (.pdf):   weasyprint HTML→PDF 管线，含 Plotly 图表截图（需 kaleido）

对外入口：
  markdown_to_word(markdown_content, title) → bytes
  markdown_to_pdf(markdown_content, title, chart_figures, chart_captions) → bytes
"""

import re
import base64
from io import BytesIO
from datetime import datetime


# ── 函数 1: markdown_to_word ─────────────────────────────────────────────────

def markdown_to_word(markdown_content: str, title: str) -> bytes:
    """
    把 Markdown 字符串转成格式化的 Word 文档，返回 bytes。

    支持：一/二/三级标题、正文、加粗、项目符号、Markdown 表格、水平线
    不嵌入图表（Word 末尾加注说明）
    """
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    # ── 页面设置 ──────────────────────────────────────────────────────────────
    section = doc.sections[0]
    section.page_width  = Cm(21)
    section.page_height = Cm(29.7)
    section.left_margin   = Cm(2.5)
    section.right_margin  = Cm(2.5)
    section.top_margin    = Cm(2)
    section.bottom_margin = Cm(2)

    # ── 页眉：报告标题右对齐 ──────────────────────────────────────────────────
    header = section.header
    header_para = header.paragraphs[0]
    header_para.text = title
    header_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header_para.style.font.size = Pt(9)
    header_para.style.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    # ── 页脚：日期左 + 页码右 ─────────────────────────────────────────────────
    footer = section.footer
    footer_para = footer.paragraphs[0]
    footer_para.clear()
    # 左侧日期
    run_date = footer_para.add_run(f"生成日期：{datetime.now().strftime('%Y-%m-%d')}")
    run_date.font.size = Pt(9)
    run_date.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    # Tab 分隔到右侧
    footer_para.add_run("\t\t")
    # 右侧页码（Word 域）
    run_pg = footer_para.add_run()
    run_pg.font.size = Pt(9)
    fldChar1 = OxmlElement("w:fldChar"); fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText"); instrText.text = "PAGE"
    fldChar2 = OxmlElement("w:fldChar"); fldChar2.set(qn("w:fldCharType"), "end")
    run_pg._r.append(fldChar1); run_pg._r.append(instrText); run_pg._r.append(fldChar2)

    # ── 辅助：段落格式 ────────────────────────────────────────────────────────
    def _para(text: str, bold=False, size=11, space_before=0, space_after=4,
              alignment=WD_ALIGN_PARAGRAPH.LEFT, color: tuple = None):
        p = doc.add_paragraph()
        p.alignment = alignment
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.space_after  = Pt(space_after)
        p.paragraph_format.line_spacing = Pt(size * 1.3)
        # 内联 **加粗** 解析
        parts = re.split(r'(\*\*[^*]+\*\*)', text)
        for part in parts:
            m = re.match(r'\*\*([^*]+)\*\*', part)
            run = p.add_run(m.group(1) if m else part)
            run.bold = bold or bool(m)
            run.font.size = Pt(size)
            if color:
                run.font.color.rgb = RGBColor(*color)
        return p

    def _add_hr(doc):
        """添加水平分割线段落。"""
        p = doc.add_paragraph()
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"),   "single")
        bottom.set(qn("w:sz"),    "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "AAAAAA")
        pBdr.append(bottom)
        pPr.append(pBdr)

    # ── 文档标题 ──────────────────────────────────────────────────────────────
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_para.paragraph_format.space_before = Pt(18)
    title_para.paragraph_format.space_after  = Pt(12)
    title_run = title_para.add_run(title)
    title_run.bold = True
    title_run.font.size = Pt(24)

    # 生成日期
    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_para.paragraph_format.space_after = Pt(12)
    date_run = date_para.add_run(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    date_run.font.size = Pt(10)
    date_run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    _add_hr(doc)

    # ── 按行解析 Markdown ─────────────────────────────────────────────────────
    lines = markdown_content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # 一级标题
        if re.match(r'^#\s+', line):
            _para(line[2:].strip(), bold=True, size=18,
                  space_before=12, space_after=6)
            i += 1; continue

        # 二级标题
        if re.match(r'^##\s+', line):
            _para(line[3:].strip(), bold=True, size=14,
                  space_before=8, space_after=4)
            i += 1; continue

        # 三级标题
        if re.match(r'^###\s+', line):
            _para(line[4:].strip(), bold=True, size=12, space_before=6)
            i += 1; continue

        # 水平线
        if re.match(r'^-{3,}\s*$', line):
            _add_hr(doc)
            i += 1; continue

        # Markdown 表格（检测到 | 开头且下一行含 ---）
        if line.startswith("|") and i + 1 < len(lines) and re.match(r'^\|[-| :]+\|', lines[i + 1]):
            # 收集表格行
            table_lines = [line]
            j = i + 1
            while j < len(lines) and lines[j].startswith("|"):
                table_lines.append(lines[j])
                j += 1
            # 解析表头 + 数据行（跳过分隔行）
            header_row = [c.strip() for c in table_lines[0].strip('|').split('|')]
            data_rows  = []
            for tl in table_lines[2:]:
                if re.match(r'^\|[-| :]+\|', tl):
                    continue
                data_rows.append([c.strip() for c in tl.strip('|').split('|')])

            n_cols = len(header_row)
            t = doc.add_table(rows=1 + len(data_rows), cols=n_cols)
            t.style = "Table Grid"

            # 表头行
            for ci, cell_text in enumerate(header_row):
                cell = t.rows[0].cells[ci]
                cell.text = cell_text
                run = cell.paragraphs[0].runs[0] if cell.paragraphs[0].runs else cell.paragraphs[0].add_run(cell_text)
                run.bold = True
                run.font.size = Pt(10)
                # 灰色底色
                tc_pr = cell._tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"),   "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "D9D9D9")
                tc_pr.append(shd)

            # 数据行
            for ri, row_data in enumerate(data_rows, start=1):
                for ci, cell_text in enumerate(row_data[:n_cols]):
                    cell = t.rows[ri].cells[ci]
                    cell.text = cell_text
                    if cell.paragraphs[0].runs:
                        cell.paragraphs[0].runs[0].font.size = Pt(10)

            doc.add_paragraph()  # 表后空行
            i = j; continue

        # 项目符号（- 或 * 开头）
        if re.match(r'^[-*]\s+', line):
            content = re.sub(r'^[-*]\s+', '', line)
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.left_indent = Cm(0.5)
            p.paragraph_format.space_after = Pt(2)
            # 内联加粗
            parts = re.split(r'(\*\*[^*]+\*\*)', content)
            for part in parts:
                m = re.match(r'\*\*([^*]+)\*\*', part)
                run = p.add_run(m.group(1) if m else part)
                run.bold = bool(m)
                run.font.size = Pt(11)
            i += 1; continue

        # 数字编号列表（1. 2. 等）
        if re.match(r'^\d+\.\s+', line):
            content = re.sub(r'^\d+\.\s+', '', line)
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.left_indent = Cm(0.5)
            p.paragraph_format.space_after = Pt(2)
            parts = re.split(r'(\*\*[^*]+\*\*)', content)
            for part in parts:
                m = re.match(r'\*\*([^*]+)\*\*', part)
                run = p.add_run(m.group(1) if m else part)
                run.bold = bool(m)
                run.font.size = Pt(11)
            i += 1; continue

        # 空行
        if not line.strip():
            i += 1; continue

        # 普通正文（支持内联加粗）
        _para(line, size=11, space_before=0, space_after=4)
        i += 1

    # ── 末尾注释：图表说明 ────────────────────────────────────────────────────
    doc.add_paragraph()
    _add_hr(doc)
    note = doc.add_paragraph()
    note.paragraph_format.space_before = Pt(6)
    note_run = note.add_run("📊 本报告图表请在 AI Agent 界面查看（Word 格式不支持交互式图表）")
    note_run.font.size = Pt(9)
    note_run.font.italic = True
    note_run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── 函数 2: export_chart_as_png ─────────────────────────────────────────────

_PNG_TIMEOUT_SEC = 25  # kaleido 首次启动 Chromium 可能很慢，超时则跳过

def export_chart_as_png(fig, width: int = 900, height: int = 450) -> bytes | None:
    """
    把 Plotly Figure 导出为 PNG bytes（需要 kaleido）。
    - 找不到 kaleido 或超时（25 秒）时返回 None，不报错，报告继续生成。
    - 用独立线程执行，防止 kaleido 启动 Chromium 时阻塞主线程。
    """
    import concurrent.futures

    def _do_export():
        return fig.to_image(format="png", width=width, height=height, scale=2)

    # 不用 `with ThreadPoolExecutor` —— 其 __exit__ 调用 shutdown(wait=True)，
    # 超时后仍会阻塞等 kaleido 线程结束。改为手动 shutdown(wait=False)。
    _ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    _f  = _ex.submit(_do_export)
    try:
        return _f.result(timeout=_PNG_TIMEOUT_SEC)
    except concurrent.futures.TimeoutError:
        print(f"[report_builder] chart export timed out after {_PNG_TIMEOUT_SEC}s, skipping")
        return None
    except Exception as e:
        print(f"[report_builder] chart export failed: {e}")
        return None
    finally:
        _ex.shutdown(wait=False)


# ── 函数 3: build_html_report ────────────────────────────────────────────────

def build_html_report(
    markdown_content: str,
    title: str,
    chart_figures: list,
    chart_captions: list,
) -> str:
    """
    把 Markdown 内容 + Plotly 图表 合并成一个完整 HTML 字符串。
    是 PDF 生成的中间产物。
    """
    import markdown as md_lib

    # Step 1: Markdown → HTML 片段
    body_html = md_lib.markdown(
        markdown_content,
        extensions=["tables", "fenced_code"],
    )

    # Step 2: 图表截图嵌入（PNG base64）
    for fig, caption in zip(chart_figures, chart_captions):
        png_bytes = export_chart_as_png(fig)
        if png_bytes:
            b64 = base64.b64encode(png_bytes).decode()
            img_tag = (
                f'<figure>'
                f'<img src="data:image/png;base64,{b64}" '
                f'style="width:100%;max-width:800px;"/>'
                f'<figcaption>{caption}</figcaption>'
                f'</figure>'
            )
            body_html += img_tag
        else:
            body_html += f'<p><em>[图表"{caption}"无法嵌入，请在 Agent 界面查看]</em></p>'

    # Step 3: 完整 HTML + CSS
    generated_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        @page {{
            size: A4;
            margin: 15mm 20mm;
            @top-right {{ content: "{title}"; font-size: 9pt; color: #888; }}
            @bottom-right {{ content: "第 " counter(page) " 页"; font-size: 9pt; color: #888; }}
            @bottom-left {{ content: "{generated_date}"; font-size: 9pt; color: #888; }}
        }}
        body {{
            font-family: 'Microsoft YaHei', 'SimHei', 'STHeiti', sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
        }}
        h1 {{
            font-size: 18pt;
            font-weight: bold;
            margin-top: 20pt;
            margin-bottom: 8pt;
            color: #1a1a2e;
            border-bottom: 2px solid #4C72B0;
            padding-bottom: 4pt;
        }}
        h2 {{
            font-size: 14pt;
            font-weight: bold;
            margin-top: 14pt;
            margin-bottom: 6pt;
            color: #1a1a2e;
        }}
        h3 {{
            font-size: 12pt;
            font-weight: bold;
            margin-top: 10pt;
            margin-bottom: 4pt;
        }}
        p {{ margin: 6pt 0; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10pt 0;
            font-size: 10pt;
        }}
        th {{
            background-color: #F2F2F2;
            font-weight: bold;
            text-align: left;
        }}
        td, th {{
            border: 1px solid #DDD;
            padding: 6px 10px;
        }}
        tr:nth-child(even) {{ background-color: #FAFAFA; }}
        img {{
            max-width: 100%;
            display: block;
            margin: 10px auto;
        }}
        figure {{
            text-align: center;
            margin: 16px 0;
        }}
        figcaption {{
            font-size: 9pt;
            color: #666;
            margin-top: 4px;
        }}
        code {{
            background: #F5F5F5;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10pt;
        }}
        pre {{
            background: #F5F5F5;
            padding: 12px;
            border-radius: 4px;
            font-size: 10pt;
            overflow-x: auto;
        }}
        ul, ol {{ padding-left: 1.5em; margin: 6pt 0; }}
        li {{ margin: 3pt 0; }}
        hr {{
            border: none;
            border-top: 1px solid #CCC;
            margin: 12pt 0;
        }}
        blockquote {{
            border-left: 4px solid #4C72B0;
            margin: 10pt 0;
            padding: 4pt 12pt;
            color: #555;
        }}
    </style>
</head>
<body>
    <h1 style="text-align:center;border-bottom:none;">{title}</h1>
    <p style="text-align:center;color:#888;font-size:9pt">
        生成时间：{generated_date}
    </p>
    <hr/>
    {body_html}
</body>
</html>"""
    return html


# ── 函数 4a: _build_pdf_safe_html（PDF 专用简化 HTML）────────────────────────

def _build_pdf_safe_html(markdown_content: str, title: str) -> str:
    """
    生成 xhtml2pdf 兼容的 HTML。
    与 build_html_report 的区别：
    - 无 @page 命名 margin boxes（@top-right 等）—— xhtml2pdf 不支持，会卡死
    - 无 :nth-child 伪选择器 —— xhtml2pdf 不支持
    - 不用 @font-face file:// URI —— 由调用方通过 reportlab API 预注册字体
    """
    import markdown as md_lib

    body_html = md_lib.markdown(
        markdown_content,
        extensions=["tables", "fenced_code"],
    )
    generated_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<title>{title}</title>
<style>
@page {{ size: A4; margin: 20mm; }}
body   {{ font-family: Arial, sans-serif; font-size: 11pt;
          line-height: 1.6; color: #333; }}
h1     {{ font-size: 18pt; font-weight: bold; color: #1a1a2e;
          border-bottom: 2px solid #4C72B0; padding-bottom: 4pt;
          margin-top: 0; text-align: center; }}
h2     {{ font-size: 14pt; font-weight: bold; color: #1a1a2e; margin-top: 14pt; }}
h3     {{ font-size: 12pt; font-weight: bold; margin-top: 10pt; }}
p      {{ margin: 6pt 0; }}
table  {{ width: 100%; border-collapse: collapse; margin: 10pt 0; font-size: 10pt; }}
th     {{ background-color: #F2F2F2; font-weight: bold; text-align: left;
          border: 1px solid #CCC; padding: 5px 8px; }}
td     {{ border: 1px solid #CCC; padding: 5px 8px; }}
ul, ol {{ padding-left: 1.5em; margin: 6pt 0; }}
li     {{ margin: 3pt 0; }}
code   {{ background: #F5F5F5; padding: 2px 4px; font-size: 9pt; }}
pre    {{ background: #F5F5F5; padding: 8px; font-size: 9pt; }}
blockquote {{ border-left: 4px solid #4C72B0; margin: 8pt 0;
              padding: 4pt 10pt; color: #555; }}
hr     {{ border: none; border-top: 1px solid #CCC; margin: 12pt 0; }}
.rpt-date {{ text-align: center; color: #888; font-size: 9pt; margin-bottom: 8pt; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="rpt-date">生成时间：{generated_date}</p>
<hr/>
{body_html}
</body>
</html>"""


# ── 函数 4b & 5: markdown_to_pdf（reportlab 直接生成）────────────────────────

# 候选中文 TTF 字体路径（按优先级）
_CJK_FONT_PATHS = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simkai.ttf",
    r"C:\Windows\Fonts\simfang.ttf",
    r"C:\Windows\Fonts\STZHONGS.TTF",
]


def _register_cjk_font() -> str:
    """注册第一个可用的 CJK TTF 字体，返回已注册的字体名。找不到返回 'Helvetica'。"""
    import os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in _CJK_FONT_PATHS:
        if not os.path.exists(path):
            continue
        font_name = "CJKFont"
        if font_name not in pdfmetrics.getRegisteredFontNames():
            try:
                pdfmetrics.registerFont(TTFont(font_name, path))
            except Exception:
                continue
        return font_name
    return "Helvetica"


def markdown_to_pdf(
    markdown_content: str,
    title: str,
    chart_figures: list = None,
    chart_captions: list = None,
) -> bytes:
    """
    Markdown → PDF，使用 reportlab 直接生成（不经过 xhtml2pdf/HTML）。
    中文字体通过 pdfmetrics.registerFont 嵌入，彻底解决乱码问题。
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, white
    pt = 1  # reportlab 坐标系本身就是 points，pt=1 是惯例
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, ListFlowable, ListItem,
    )

    FONT    = _register_cjk_font()
    C_DARK  = HexColor("#1a1a2e")
    C_BLUE  = HexColor("#4C72B0")
    C_GRAY  = HexColor("#888888")
    C_LIGHT = HexColor("#EEF2FA")   # 表头背景，蓝调
    C_ROW2  = HexColor("#F8F9FC")   # 偶数行背景
    C_BDR   = HexColor("#C8D0DC")   # 表格边框

    def S(name, **kw):
        return ParagraphStyle(name, fontName=FONT, **kw)

    # 样式对照网页版：标题大且居中，H2 明显加大，表头加粗
    s_title  = S("T",  fontSize=20, textColor=C_DARK, alignment=1,
                 spaceAfter=6*pt, leading=26)
    s_date   = S("D",  fontSize=9,  textColor=C_GRAY, alignment=1,
                 spaceAfter=14*pt, leading=13)
    s_h1     = S("H1", fontSize=16, textColor=C_DARK, spaceBefore=14*pt,
                 spaceAfter=5*pt,  leading=22)
    s_h2     = S("H2", fontSize=14, textColor=C_DARK, spaceBefore=12*pt,
                 spaceAfter=4*pt,  leading=20)
    s_h3     = S("H3", fontSize=11, textColor=HexColor("#2c3e6e"),
                 spaceBefore=9*pt, spaceAfter=3*pt, leading=16)
    s_body   = S("B",  fontSize=10, textColor=HexColor("#333333"),
                 spaceAfter=5*pt,  leading=17)
    s_bullet = S("BL", fontSize=10, textColor=HexColor("#333333"),
                 spaceAfter=3*pt,  leading=16, leftIndent=14*pt, firstLineIndent=0)
    s_num    = S("NL", fontSize=10, textColor=HexColor("#333333"),
                 spaceAfter=3*pt,  leading=16, leftIndent=18*pt, firstLineIndent=-18*pt)
    s_cell   = S("C",  fontSize=9,  textColor=HexColor("#333333"), leading=14)
    s_hcell  = S("HC", fontSize=9,  textColor=HexColor("#1a1a2e"),  leading=14)

    # ── 符号安全转换 ─────────────────────────────────────────────────────────
    # ¥（全角 U+FFE5）→ ¥（半角 U+00A5），SimHei 有半角 ¥ 字形
    # 常见特殊符号保留，不做替换
    _SYM_MAP = {
        "￥": "¥",   # ￥ → ¥
        "’": "'",         # 右单引号
        "‘": "'",         # 左单引号
        "“": '"',         # 左双引号
        "”": '"',         # 右双引号
        "–": "-",         # en dash
        "—": "--",        # em dash
    }

    def inline(text: str) -> str:
        """XML 转义 + 符号规范化 + **bold** → <b>。"""
        for src, dst in _SYM_MAP.items():
            text = text.replace(src, dst)
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        return text

    buf  = BytesIO()
    doc  = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=22*mm,   bottomMargin=20*mm,
        title=title,
    )
    story = []
    generated_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 封面区
    story.append(Paragraph(inline(title), s_title))
    story.append(HRFlowable(width="100%", thickness=2, color=C_BLUE, spaceAfter=4*pt))
    story.append(Paragraph(f"生成时间：{generated_date}", s_date))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BDR))
    story.append(Spacer(1, 8*pt))

    lines   = markdown_content.split("\n")
    i       = 0
    avail_w = A4[0] - 40*mm

    while i < len(lines):
        line     = lines[i]
        stripped = line.strip()

        if re.match(r'^# [^#]', stripped):
            story.append(Paragraph(inline(stripped[2:]), s_h1))
            story.append(HRFlowable(width="100%", thickness=1, color=C_BLUE, spaceAfter=4*pt))
            i += 1

        elif re.match(r'^## [^#]', stripped):
            story.append(Spacer(1, 2*pt))
            story.append(Paragraph(inline(stripped[3:]), s_h2))
            story.append(HRFlowable(width="60%", thickness=0.8, color=C_BLUE,
                                    spaceAfter=3*pt))
            i += 1

        elif re.match(r'^### ', stripped):
            story.append(Paragraph(inline(stripped[4:]), s_h3))
            i += 1

        elif re.match(r'^-{3,}$', stripped):
            story.append(HRFlowable(width="100%", thickness=0.5, color=C_BDR))
            story.append(Spacer(1, 4*pt))
            i += 1

        elif re.match(r'^[-*] ', stripped):
            # ── 无序列表：用 Paragraph 直接加 • 前缀，避免 ListFlowable 字形问题
            while i < len(lines) and re.match(r'^[-*] ', lines[i].strip()):
                txt = inline(lines[i].strip()[2:])
                story.append(Paragraph(f"• {txt}", s_bullet))
                i += 1

        elif re.match(r'^\d+\. ', stripped):
            # ── 有序列表：编号写入段落文字，保持对齐
            num = 1
            while i < len(lines) and re.match(r'^\d+\. ', lines[i].strip()):
                txt = inline(re.sub(r'^\d+\. ', '', lines[i].strip()))
                story.append(Paragraph(f"{num}. {txt}", s_num))
                i += 1
                num += 1

        elif stripped.startswith("|"):
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i].strip())
                i += 1
            # 跳过分隔行（|:---|:---:|）
            tbl_lines = [l for l in tbl_lines
                         if not re.match(r'^\|[\s\-|:]+\|$', l)]
            if tbl_lines:
                raw_data = []
                for tl in tbl_lines:
                    raw_data.append([c.strip() for c in tl.strip("|").split("|")])
                n_cols = max(len(r) for r in raw_data)
                for row in raw_data:
                    while len(row) < n_cols:
                        row.append("")
                col_w = avail_w / n_cols
                pdf_data = []
                for ri, row in enumerate(raw_data):
                    sty = s_hcell if ri == 0 else s_cell
                    pdf_data.append([Paragraph(inline(c), sty) for c in row])
                t = Table(pdf_data, colWidths=[col_w] * n_cols, repeatRows=1)
                ts = [
                    ("BACKGROUND",    (0, 0),  (-1, 0),  C_LIGHT),
                    ("FONTNAME",      (0, 0),  (-1, -1), FONT),
                    ("FONTSIZE",      (0, 0),  (-1, -1), 9),
                    ("FONTNAME",      (0, 0),  (-1, 0),  FONT),   # 表头同字体，靠 BOLD 加粗
                    ("BOLD",          (0, 0),  (-1, 0),  True),   # 仅在 reportlab >= 3.5 有效
                    ("GRID",          (0, 0),  (-1, -1), 0.5, C_BDR),
                    ("TOPPADDING",    (0, 0),  (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0),  (-1, -1), 5),
                    ("LEFTPADDING",   (0, 0),  (-1, -1), 7),
                    ("RIGHTPADDING",  (0, 0),  (-1, -1), 7),
                    ("LINEABOVE",     (0, 0),  (-1, 0),  1.5, C_BLUE),  # 表头顶部粗线
                    ("LINEBELOW",     (0, 0),  (-1, 0),  1,   C_BLUE),  # 表头底部线
                ]
                for ri in range(1, len(pdf_data)):
                    bg = C_ROW2 if ri % 2 == 0 else white
                    ts.append(("BACKGROUND", (0, ri), (-1, ri), bg))
                t.setStyle(TableStyle(ts))
                story.append(t)
                story.append(Spacer(1, 8*pt))

        elif stripped == "":
            story.append(Spacer(1, 3*pt))
            i += 1

        else:
            story.append(Paragraph(inline(stripped), s_body))
            i += 1

    doc.build(story)
    return buf.getvalue()


def html_to_pdf(html_content: str) -> bytes:
    """保留供外部调用；内部已改用 markdown_to_pdf（reportlab）。"""
    raise NotImplementedError(
        "html_to_pdf 已废弃，请改用 markdown_to_pdf(markdown_content, title)。"
    )
