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

def export_chart_as_png(fig, width: int = 1100, height: int = 500) -> bytes | None:
    """
    把 Plotly Figure 导出为 PNG bytes（需要 kaleido）。
    默认 scale=2，实际像素 2200×1000，满足 A4 高清打印。
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

# 专业报告 CSS（深海蓝 #1B3A6B + 橙色 #E87722，微软雅黑优先）
_HTML_REPORT_CSS = """
@page {
    size: A4;
    margin: 20mm 22mm 25mm 22mm;
    @top-center {
        content: element(header);
        vertical-align: bottom;
    }
    @bottom-left {
        content: "Confidential";
        font-size: 8pt;
        color: #9CA3AF;
        font-family: 'Microsoft YaHei', sans-serif;
    }
    @bottom-right {
        content: "第 " counter(page) " 页 / 共 " counter(pages) " 页";
        font-size: 8pt;
        color: #6B7280;
        font-family: 'Microsoft YaHei', sans-serif;
    }
}

#page-header {
    position: running(header);
    width: 100%;
    border-bottom: 2px solid #1B3A6B;
    padding-bottom: 4pt;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
#page-header .header-title {
    font-size: 8.5pt;
    color: #1B3A6B;
    font-weight: 600;
    font-family: 'Microsoft YaHei', sans-serif;
}
#page-header .header-date {
    font-size: 8pt;
    color: #9CA3AF;
    font-family: 'Microsoft YaHei', sans-serif;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Microsoft YaHei', 'PingFang SC', 'STHeiti',
                 'WenQuanYi Micro Hei', 'Noto Sans CJK SC', sans-serif;
    font-size: 10.5pt;
    line-height: 1.75;
    color: #2C2C2C;
    background: white;
}

.cover {
    text-align: center;
    padding: 60pt 30pt 40pt 30pt;
    border-bottom: 4px solid #1B3A6B;
    margin-bottom: 36pt;
    page-break-after: always;
}
.cover-tag {
    display: inline-block;
    background: #E87722;
    color: white;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 3pt 10pt;
    border-radius: 2pt;
    margin-bottom: 20pt;
    text-transform: uppercase;
}
.cover-title {
    font-size: 24pt;
    font-weight: 700;
    color: #1B3A6B;
    line-height: 1.3;
    margin-bottom: 16pt;
}
.cover-subtitle {
    font-size: 11pt;
    color: #6B7280;
    margin-bottom: 32pt;
}
.cover-meta {
    font-size: 9pt;
    color: #9CA3AF;
    border-top: 1px solid #E5E7EB;
    padding-top: 16pt;
}
.cover-meta span { margin: 0 12pt; }

h1 {
    font-size: 16pt;
    font-weight: 700;
    color: #1B3A6B;
    margin-top: 30pt;
    margin-bottom: 12pt;
    padding-bottom: 6pt;
    border-bottom: 2.5px solid #1B3A6B;
    page-break-after: avoid;
}
h1 .section-num {
    display: inline-block;
    background: #1B3A6B;
    color: white;
    font-size: 9pt;
    padding: 1pt 7pt;
    border-radius: 2pt;
    margin-right: 8pt;
    vertical-align: middle;
}
h2 {
    font-size: 13pt;
    font-weight: 700;
    color: #1B3A6B;
    margin-top: 22pt;
    margin-bottom: 8pt;
    padding-left: 10pt;
    border-left: 4px solid #E87722;
    page-break-after: avoid;
}
h3 {
    font-size: 11pt;
    font-weight: 600;
    color: #374151;
    margin-top: 16pt;
    margin-bottom: 6pt;
    page-break-after: avoid;
}
p {
    margin-bottom: 9pt;
    text-align: justify;
    orphans: 3;
    widows: 3;
}
strong { color: #1B3A6B; font-weight: 700; }
ul, ol { margin: 8pt 0 10pt 18pt; }
li { margin-bottom: 4pt; line-height: 1.7; }
li::marker { color: #E87722; }

table {
    width: 100%;
    border-collapse: collapse;
    margin: 14pt 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}
thead tr { background: #1B3A6B; color: white; }
thead th {
    padding: 8pt 10pt;
    text-align: left;
    font-weight: 600;
    font-size: 9pt;
    letter-spacing: 0.3px;
}
thead th:first-child, tbody td:first-child { text-align: center; }
tbody tr:nth-child(even) { background: #F5F7FA; }
tbody tr:hover { background: #EFF6FF; }
tbody td {
    padding: 7pt 10pt;
    border-bottom: 1px solid #E5E7EB;
    color: #374151;
}
tbody td:not(:first-child):not(:nth-child(2)) { text-align: right; }
tbody tr.highlight td { font-weight: 700; color: #1B3A6B; }
.table-caption {
    font-size: 9pt; color: #6B7280;
    text-align: center; margin-top: -8pt; margin-bottom: 12pt; font-style: italic;
}

.chart-container {
    margin: 16pt 0;
    text-align: center;
    page-break-inside: avoid;
}
.chart-container img {
    max-width: 100%;
    border: 1px solid #E5E7EB;
    border-radius: 4pt;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.chart-caption {
    font-size: 8.5pt; color: #6B7280;
    margin-top: 6pt; font-style: italic; text-align: center;
}
.chart-number { font-weight: 700; color: #1B3A6B; }

.page-break { page-break-before: always; }
.no-break { page-break-inside: avoid; }

.appendix {
    border-top: 2px solid #E5E7EB;
    margin-top: 30pt;
    padding-top: 20pt;
}
.appendix h1 { color: #6B7280; border-bottom-color: #E5E7EB; font-size: 14pt; }

.watermark {
    position: fixed;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%) rotate(-35deg);
    font-size: 60pt;
    color: rgba(27, 58, 107, 0.04);
    font-weight: 900;
    pointer-events: none;
    z-index: -1;
    white-space: nowrap;
}
"""


def _chart_html(chart_n: int, b64: str, caption: str) -> str:
    """生成单张图表的 HTML 片段。"""
    return (
        f'<div class="chart-container">'
        f'<img src="data:image/png;base64,{b64}" alt="{caption}"/>'
        f'<p class="chart-caption">'
        f'<span class="chart-number">图{chart_n}</span> {caption}'
        f'</p></div>'
    )


def _match_chart_for_section(section_title: str, unplaced: list) -> dict | None:
    """
    按两级优先级为章节标题匹配最合适的图表。
    优先级1：图表标题包含章节关键词（bigram 或英文词）。
    优先级2：章节与图表标题的 bigram 集合有交集。
    匹配到后将 chart dict 的 'placed' 设为 True 并返回。
    """
    def keywords(s: str) -> set:
        """提取关键词：汉字连续串的所有 2-gram + 3字以上英文词。"""
        result = set()
        # 英文词（3字以上）
        for w in re.findall(r'[a-zA-Z]{3,}', s):
            result.add(w.lower())
        # 汉字连续串 → 逐个 2-gram
        for run in re.findall(r'[一-鿿]+', s):
            for i in range(len(run) - 1):
                result.add(run[i:i + 2])
        return result

    sec_kw = keywords(section_title)
    if not sec_kw:
        return None

    # 优先级 1：图表标题作为字符串直接包含章节中的某个关键词
    for c in unplaced:
        for w in sec_kw:
            if w in c['caption']:
                c['placed'] = True
                return c
    # 优先级 2：关键词集合有交集
    for c in unplaced:
        if sec_kw & keywords(c['caption']):
            c['placed'] = True
            return c
    return None


def build_html_report(
    markdown_content: str,
    title: str,
    chart_figures: list = None,
    chart_captions: list = None,
    generated_date: str = None,
) -> str:
    """
    把 Markdown 报告内容 + Plotly 图表合并为专业排版的 HTML。

    图表匹配规则：
    - 按章节（## 标题）关键词匹配，优先完全包含，其次关键词交集
    - 匹配到的图表嵌入对应章节末尾；未匹配的图表汇总到附图附录
    """
    import markdown as md_lib

    chart_figures  = chart_figures  or []
    chart_captions = chart_captions or []
    if not generated_date:
        generated_date = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    # ── Step 1: 导出所有图表为 base64 PNG ──────────────────────────────────────
    chart_data = []
    for i, (fig, cap) in enumerate(zip(chart_figures, chart_captions)):
        png_bytes = export_chart_as_png(fig, width=1100, height=500)
        if png_bytes:
            chart_data.append({
                'index':   i + 1,
                'caption': cap,
                'b64':     base64.b64encode(png_bytes).decode(),
                'placed':  False,
            })

    # ── Step 2: Markdown → HTML ────────────────────────────────────────────────
    body_html = md_lib.markdown(
        markdown_content,
        extensions=['tables', 'fenced_code', 'nl2br'],
    )

    # ── Step 3: 按 <h2> 章节分段，匹配并插入图表 ─────────────────────────────
    # 用 re.split 把 body_html 按 <h2>...</h2> 切割
    # 结果格式：[before_h2, h2_tag, section_content, h2_tag, section_content, ...]
    parts = re.split(r'(<h2>[^<]*</h2>)', body_html)

    result_parts = []
    chart_n = 0  # 全局图表编号
    unplaced = [c for c in chart_data]  # 尚未放置的图表（共享引用）

    for idx, part in enumerate(parts):
        result_parts.append(part)
        m = re.match(r'<h2>([^<]*)</h2>', part)
        if not m:
            continue
        section_title = m.group(1)
        # 在 unplaced 里找本章节图表，插入到下一个 h2 之前（即当前 section_content 末尾）
        # section_content 在 parts[idx+1]（如果存在）
        # 不修改 parts[idx+1]；改为在 parts[idx+1] 之后插入图表 HTML
        matched = _match_chart_for_section(section_title, [c for c in unplaced if not c['placed']])
        if matched:
            chart_n += 1
            matched['placed'] = True
            matched['chart_n'] = chart_n  # 更新实际编号
            # 将图表注入紧跟在该章节内容之后
            # 找到本 h2 对应的 section_content（parts[idx+1]），在其末尾插入
            if idx + 1 < len(parts):
                result_parts.append(parts[idx + 1])   # section content
                result_parts.append(_chart_html(chart_n, matched['b64'], matched['caption']))
                # 跳过 parts[idx+1]，否则会被再次 append 在下一轮
                parts[idx + 1] = ''  # 已处理，清空防止重复
            else:
                result_parts.append(_chart_html(chart_n, matched['b64'], matched['caption']))

    body_with_charts = ''.join(result_parts)

    # ── Step 4: 未匹配图表放附录 ───────────────────────────────────────────────
    still_unplaced = [c for c in chart_data if not c['placed']]
    appendix_html = ''
    if still_unplaced:
        appendix_html = '<div class="appendix"><h1>附图</h1>'
        for c in still_unplaced:
            chart_n += 1
            appendix_html += _chart_html(chart_n, c['b64'], c['caption'])
        appendix_html += '</div>'

    # ── Step 5: 组装完整 HTML ──────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>{_HTML_REPORT_CSS}</style>
</head>
<body>
    <div class="watermark">CONFIDENTIAL</div>
    <div id="page-header">
        <span class="header-title">{title}</span>
        <span class="header-date">{generated_date}</span>
    </div>
    <div class="cover">
        <div class="cover-tag">Analysis Report</div>
        <div class="cover-title">{title}</div>
        <div class="cover-subtitle">AI 数据分析 Agent 自动生成</div>
        <div class="cover-meta">
            <span>生成时间: {generated_date}</span>
            <span>数据来源: Olist Brazilian E-Commerce</span>
        </div>
    </div>
    {body_with_charts}
    {appendix_html}
</body>
</html>"""


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

# 候选中文字体路径（按优先级）；.ttc 用 subfontIndex=0 加载
_CJK_FONT_PATHS = [
    r"C:\Windows\Fonts\msyh.ttc",       # 微软雅黑 Regular（Win10/11，字形最全）
    r"C:\Windows\Fonts\msyh.ttf",       # 部分系统为 TTF 格式
    r"C:\Windows\Fonts\msyhbd.ttc",     # 微软雅黑 Bold（备用）
    r"C:\Windows\Fonts\simhei.ttf",     # 黑体（旧系统备选）
    r"C:\Windows\Fonts\simkai.ttf",
    r"C:\Windows\Fonts\simfang.ttf",
    r"C:\Windows\Fonts\STZHONGS.TTF",
]


def _register_cjk_font() -> tuple:
    """
    注册第一个可用的 CJK 字体（TTF/TTC），返回 (字体名, 字体路径)。
    找不到可用字体时返回 ('Helvetica', '')。
    """
    import os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in _CJK_FONT_PATHS:
        if not os.path.exists(path):
            continue
        font_name = "CJKFont"
        if font_name not in pdfmetrics.getRegisteredFontNames():
            try:
                if path.lower().endswith(".ttc"):
                    pdfmetrics.registerFont(TTFont(font_name, path, subfontIndex=0))
                else:
                    pdfmetrics.registerFont(TTFont(font_name, path))
            except Exception:
                continue
        return font_name, path
    return "Helvetica", ""


def markdown_to_pdf(
    markdown_content: str,
    title: str,
    chart_figures: list = None,
    chart_captions: list = None,
    chart_png_bytes: list = None,
) -> bytes:
    """
    Markdown → PDF，使用 reportlab 直接生成（不经过 xhtml2pdf/HTML）。
    中文字体通过 pdfmetrics.registerFont 嵌入，彻底解决乱码问题。
    chart_png_bytes: 可选，预先导出的 PNG bytes 列表（与 chart_figures 等长）。
    传入时直接使用，跳过 export_chart_as_png，避免在 60s 超时内串行导出超时。
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, white
    pt = 1
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, KeepTogether,
    )

    FONT, _font_path = _register_cjk_font()
    _is_yahe = "msyh" in _font_path.lower()

    # ── 颜色（与 HTML CSS 完全对齐）──────────────────────────────────────────
    C_NAVY   = HexColor("#1B3A6B")   # 深海蓝：标题、边框、表头
    C_ORANGE = HexColor("#E87722")   # 橙色：h2 左边框、badge
    C_DARK   = HexColor("#2C2C2C")   # 正文深灰
    C_GRAY   = HexColor("#6B7280")   # 辅助中灰
    C_LIGHT  = HexColor("#F5F7FA")   # 偶数行背景
    C_BDR    = HexColor("#E5E7EB")   # 边框浅灰
    C_META   = HexColor("#9CA3AF")   # 封面元数据灰

    def S(name, **kw):
        return ParagraphStyle(name, fontName=FONT, **kw)

    # ── 样式定义（对照 HTML CSS）─────────────────────────────────────────────
    # 封面
    s_badge    = S("BDG", fontSize=8,  textColor=white,   alignment=1,
                   leading=10,  spaceAfter=0)
    s_title    = S("T",   fontSize=24, textColor=C_NAVY,  alignment=1,
                   leading=30,  spaceBefore=0, spaceAfter=10*pt)
    s_subtitle = S("SUB", fontSize=11, textColor=C_GRAY,  alignment=1,
                   leading=16,  spaceAfter=24*pt)
    s_meta     = S("MTA", fontSize=9,  textColor=C_META,  alignment=1,
                   leading=13,  spaceAfter=0)
    # 正文
    s_date     = S("D",   fontSize=9,  textColor=C_GRAY,  alignment=1,
                   leading=13,  spaceAfter=6*pt)
    s_h1       = S("H1",  fontSize=16, textColor=C_NAVY,
                   spaceBefore=22*pt, spaceAfter=6*pt, leading=22)
    s_h2_text  = S("H2T", fontSize=13, textColor=C_NAVY,
                   spaceBefore=0, spaceAfter=0, leading=20)
    s_h3       = S("H3",  fontSize=11, textColor=HexColor("#374151"),
                   spaceBefore=9*pt, spaceAfter=3*pt, leading=16)
    s_body     = S("B",   fontSize=10, textColor=C_DARK,
                   spaceAfter=6*pt, leading=17)
    s_bullet   = S("BL",  fontSize=10, textColor=C_DARK,
                   spaceAfter=3*pt, leading=16, leftIndent=14*pt)
    s_num      = S("NL",  fontSize=10, textColor=C_DARK,
                   spaceAfter=3*pt, leading=16, leftIndent=18*pt, firstLineIndent=-18*pt)
    s_cell     = S("C",   fontSize=9,  textColor=HexColor("#374151"), leading=14)
    s_hcell    = S("HC",  fontSize=9,  textColor=white,  leading=14)

    def _h2_flowable(text: str) -> Table:
        """H2：用 Table + LINEBEFORE 模拟 CSS border-left: 4px solid #E87722。"""
        cell = Paragraph(text, s_h2_text)
        tbl  = Table([[cell]], colWidths=[avail_w])
        tbl.setStyle(TableStyle([
            ("LEFTPADDING",    (0, 0), (-1, -1), 12),
            ("RIGHTPADDING",   (0, 0), (-1, -1), 0),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
            ("LINEBEFORE",     (0, 0), (0,  -1), 4, C_ORANGE),
        ]))
        return tbl

    # ── 符号安全转换 ─────────────────────────────────────────────────────────
    # 层1：不管用哪种字体都要转（XML 安全 + 全角半角统一）
    _SYM_ALWAYS = {
        '￥': '¥',      # ￿e5(full-width) -> ¥ (half-width yen/yuan)
        '‘': "'",         # ‘ left single curly quote
        '’': "'",         # ’ right single curly quote
        '“': '"',         # “ left double curly quote
        '”': '"',         # ” right double curly quote
        '–': '-',          # en dash
        '—': '--',         # em dash
        '…': '...',        # ellipsis
        **{chr(0xFF01 + i): chr(0x21 + i) for i in range(94)},  # full-width ASCII -> half
    }
    _SYM_FALLBACK = {   # only applied when font is NOT YaHei (SimHei fallback)
        '×':   'x',     # x (multiplication)
        '÷':   '/',     # / (division)
        '±':   '+/-',   # +/- (plus-minus)
        '≥': '>=',    # >=
        '≤': '<=',    # <=
        '≠': '!=',    # !=
        '≈': '~=',    # approximately
        '√': 'sqrt',  # sqrt
        '∞': 'inf',   # infinity
        '∑': 'sum',   # sum
        '→': '->',    # right arrow
        '←': '<-',    # left arrow
        '↑': '^',     # up arrow
        '↓': 'v',     # down arrow
        '▲': '(+)',   # up triangle
        '▼': '(-)',   # down triangle
        '©':   '(c)',   # copyright
        '®':   '(R)',   # registered
        '™': '(TM)',  # trademark
        '·':   '.',     # middle dot
        **{chr(0x2460 + i): str(i + 1) for i in range(20)},  # circled 1-20
    }
    _SYM_MAP = dict(_SYM_ALWAYS)
    if not _is_yahe:
        _SYM_MAP.update(_SYM_FALLBACK)

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

    lines   = markdown_content.split("\n")
    i       = 0
    avail_w = A4[0] - 40*mm

    # ── 封面页（对照 HTML cover 设计）────────────────────────────────────────
    # "ANALYSIS REPORT" 橙色 badge（居中 Table）
    badge_tbl = Table([[Paragraph("ANALYSIS REPORT", s_badge)]],
                      colWidths=[70*mm])
    badge_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_ORANGE),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ]))
    badge_tbl.hAlign = "CENTER"

    cover = KeepTogether([
        Spacer(1, 50*pt),
        badge_tbl,
        Spacer(1, 18*pt),
        Paragraph(inline(title), s_title),
        Paragraph("AI 数据分析 Agent 自动生成", s_subtitle),
        HRFlowable(width="100%", thickness=1, color=C_BDR, spaceAfter=12*pt),
        Paragraph(
            f"生成时间：{generated_date}　　数据来源：Olist Brazilian E-Commerce",
            s_meta,
        ),
        Spacer(1, 36*pt),
        HRFlowable(width="100%", thickness=4, color=C_NAVY),
    ])
    story.append(cover)
    story.append(PageBreak())

    # ── 图表嵌入：预计算 section→chart 映射 ───────────────────────────────────
    _chart_figs  = chart_figures   or []
    _chart_caps  = chart_captions  or []
    _chart_bytes = chart_png_bytes or [None] * len(_chart_figs)
    _pdf_charts  = [
        {'caption': cap, 'fig': fig, 'png': png, 'placed': False}
        for fig, cap, png in zip(_chart_figs, _chart_caps, _chart_bytes)
    ]
    _sec_titles = re.findall(r'^## +(.+)$', markdown_content, re.MULTILINE)
    _sec_chart_map = {}
    for _si, _st in enumerate(_sec_titles):
        _candidates = [c for c in _pdf_charts if not c['placed']]
        _mc = _match_chart_for_section(_st, _candidates)
        if _mc:
            _sec_chart_map[_si] = _mc
    _cur_sec = [-1]  # list 让闭包内可修改

    def _add_sec_chart():
        """把当前章节匹配的图表插入 story；无可用图表或导出失败时直接跳过。"""
        idx = _cur_sec[0]
        if idx < 0:
            return
        c = _sec_chart_map.get(idx)
        if c is None:
            return
        png = c.get('png') or export_chart_as_png(c['fig'])
        if png is None:
            return
        c['png'] = png  # 缓存，避免重复导出
        from reportlab.platypus import Image as _RLImage
        story.append(Spacer(1, 6 * pt))
        story.append(_RLImage(BytesIO(png), width=avail_w, height=avail_w * 500 / 1100))
        story.append(Paragraph(f"图: {c['caption']}", s_date))
        story.append(Spacer(1, 8 * pt))

    while i < len(lines):
        line     = lines[i]
        stripped = line.strip()

        if re.match(r'^# [^#]', stripped):
            story.append(Paragraph(inline(stripped[2:]), s_h1))
            story.append(HRFlowable(width="100%", thickness=2, color=C_NAVY, spaceAfter=5*pt))
            i += 1

        elif re.match(r'^## [^#]', stripped):
            _add_sec_chart()           # 把上一章节匹配的图表插在章节末尾
            _cur_sec[0] += 1
            story.append(Spacer(1, 14*pt))
            story.append(_h2_flowable(inline(stripped[3:])))
            story.append(Spacer(1, 5*pt))
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
                    # 表头：深海蓝背景 + 白色文字（对齐 HTML）
                    ("BACKGROUND",    (0, 0),  (-1, 0),  C_NAVY),
                    ("TEXTCOLOR",     (0, 0),  (-1, 0),  white),
                    ("FONTNAME",      (0, 0),  (-1, -1), FONT),
                    ("FONTSIZE",      (0, 0),  (-1, -1), 9),
                    ("BOLD",          (0, 0),  (-1, 0),  True),
                    # 边框：仅底部分割线，无竖线（接近 HTML 表格风格）
                    ("LINEBELOW",     (0, 0),  (-1, -2), 0.5, C_BDR),
                    ("TOPPADDING",    (0, 0),  (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0),  (-1, -1), 6),
                    ("LEFTPADDING",   (0, 0),  (-1, -1), 8),
                    ("RIGHTPADDING",  (0, 0),  (-1, -1), 8),
                ]
                for ri in range(1, len(pdf_data)):
                    bg = C_LIGHT if ri % 2 == 0 else white
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

    # 最后一个章节的图表
    _add_sec_chart()

    # 未匹配的图表统一追加到附录
    _unplaced = [c for c in _pdf_charts if not c['placed']]
    if _unplaced:
        story.append(Spacer(1, 12 * pt))
        story.append(HRFlowable(width="100%", thickness=1, color=C_BDR))
        story.append(Spacer(1, 4 * pt))
        story.append(Paragraph("附图", s_h1))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_BLUE, spaceAfter=4 * pt))
        for _c in _unplaced:
            _png = _c.get('png') or export_chart_as_png(_c['fig'])
            if _png is not None:
                from reportlab.platypus import Image as _RLImage
                story.append(_RLImage(BytesIO(_png), width=avail_w, height=avail_w * 500 / 1100))
                story.append(Paragraph(f"图: {_c['caption']}", s_date))
                story.append(Spacer(1, 8 * pt))

    doc.build(story)
    return buf.getvalue()


def html_to_pdf(html_content: str) -> bytes:
    """保留供外部调用；内部已改用 markdown_to_pdf（reportlab）。"""
    raise NotImplementedError(
        "html_to_pdf 已废弃，请改用 markdown_to_pdf(markdown_content, title)。"
    )
