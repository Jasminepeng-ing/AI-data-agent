PDF报告优化
我的 AI 数据分析 Agent 已经实现了报告生成功能,当前存在两个问题需要修复:

问题 1: PDF 报告格式丑陋——字体、标题、表格样式均使用默认样式,缺乏专业感
问题 2: 生成完整报告时只有文字和表格,没有图表——当前 chart_registry 已实现
        (make_chart 每次执行时会把 fig 和 caption 存入
         st.session_state['chart_registry']),但报告生成时没有把图表嵌入对应章节

【当前代码结构说明】

- src/report_builder.py: 负责 Word 和 PDF 的构建
  - markdown_to_pdf(markdown_content, title, chart_figures, chart_captions) -> bytes
  - build_html_report(markdown_content, title, chart_figures, chart_captions) -> str
  - export_chart_as_png(fig, width, height) -> bytes | None
  - html_to_pdf(html_content) -> bytes

- src/tools.py 中的 generate_report:
  - 从 session_state['chart_registry'] 读取本轮图表
  - 调用 report_builder.markdown_to_pdf 生成 PDF

- st.session_state['chart_registry'] 的数据结构:
  [
    {
      'fig': <plotly Figure 对象>,
      'caption': '图表标题字符串',
      'timestamp': '2026-05-06T11:42:00'
    },
    ...
  ]

【任务一: 重新设计 PDF 样式(修改 build_html_report 中的 CSS)】

要求将现有 CSS 完全替换为以下专业风格设计:

设计规范:
- 主色调: 深海蓝 #1B3A6B
- 强调色: 橙色 #E87722
- 正文颜色: 深灰 #2C2C2C
- 辅助色: 中灰 #6B7280、浅灰 #F5F7FA
- 字体优先级: 'Microsoft YaHei'(微软雅黑), 'PingFang SC', 'STHeiti',
              'WenQuanYi Micro Hei', 'Noto Sans CJK SC', sans-serif

请实现以下完整 CSS(替换 build_html_report 中的 <style> 内容):

------- CSS 开始 -------

@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap');

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

/* 页眉(running element) */
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

/* 基础 */
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Microsoft YaHei', 'PingFang SC', 'STHeiti',
                 'WenQuanYi Micro Hei', sans-serif;
    font-size: 10.5pt;
    line-height: 1.75;
    color: #2C2C2C;
    background: white;
}

/* 封面区域 */
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
.cover-meta span {
    margin: 0 12pt;
}

/* 一级标题 */
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

/* 章节序号小标签(配合 Python 自动插入) */
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

/* 二级标题 */
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

/* 三级标题 */
h3 {
    font-size: 11pt;
    font-weight: 600;
    color: #374151;
    margin-top: 16pt;
    margin-bottom: 6pt;
    page-break-after: avoid;
}

/* 正文段落 */
p {
    margin-bottom: 9pt;
    text-align: justify;
    orphans: 3;
    widows: 3;
}

/* 加粗 */
strong {
    color: #1B3A6B;
    font-weight: 700;
}

/* 列表 */
ul, ol {
    margin: 8pt 0 10pt 18pt;
}
li {
    margin-bottom: 4pt;
    line-height: 1.7;
}
li::marker {
    color: #E87722;
}

/* 关键指标卡片(用于核心发现) */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10pt;
    margin: 16pt 0;
}
.metric-card {
    background: #F5F7FA;
    border-left: 4px solid #1B3A6B;
    border-radius: 4pt;
    padding: 10pt 12pt;
}
.metric-label {
    font-size: 8.5pt;
    color: #6B7280;
    margin-bottom: 4pt;
}
.metric-value {
    font-size: 16pt;
    font-weight: 700;
    color: #1B3A6B;
}
.metric-note {
    font-size: 8pt;
    color: #9CA3AF;
    margin-top: 3pt;
}

/* 洞察框(分析段落使用) */
.insight-box {
    background: linear-gradient(135deg, #EFF6FF 0%, #F5F7FA 100%);
    border: 1px solid #BFDBFE;
    border-left: 4px solid #1B3A6B;
    border-radius: 4pt;
    padding: 10pt 14pt;
    margin: 12pt 0;
    font-size: 10pt;
    color: #1E3A5F;
}
.insight-box::before {
    content: "💡 洞察";
    display: block;
    font-weight: 700;
    font-size: 8.5pt;
    color: #1B3A6B;
    margin-bottom: 5pt;
    letter-spacing: 1px;
}

/* 建议框 */
.recommend-box {
    background: #FFF7ED;
    border: 1px solid #FED7AA;
    border-left: 4px solid #E87722;
    border-radius: 4pt;
    padding: 10pt 14pt;
    margin: 12pt 0;
}
.recommend-box::before {
    content: "✅ 建议";
    display: block;
    font-weight: 700;
    font-size: 8.5pt;
    color: #C2410C;
    margin-bottom: 5pt;
    letter-spacing: 1px;
}

/* 表格 */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 14pt 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}
thead tr {
    background: #1B3A6B;
    color: white;
}
thead th {
    padding: 8pt 10pt;
    text-align: left;
    font-weight: 600;
    font-size: 9pt;
    letter-spacing: 0.3px;
}
/* 首列(排名/序号)居中 */
thead th:first-child,
tbody td:first-child {
    text-align: center;
}
tbody tr:nth-child(even) {
    background: #F5F7FA;
}
tbody tr:hover {
    background: #EFF6FF;
}
tbody td {
    padding: 7pt 10pt;
    border-bottom: 1px solid #E5E7EB;
    color: #374151;
}
/* 数值列右对齐 */
tbody td:not(:first-child):not(:nth-child(2)) {
    text-align: right;
}
/* 强调行(Top 1) */
tbody tr.highlight td {
    font-weight: 700;
    color: #1B3A6B;
}
/* 表格标题 */
.table-caption {
    font-size: 9pt;
    color: #6B7280;
    text-align: center;
    margin-top: -8pt;
    margin-bottom: 12pt;
    font-style: italic;
}

/* 图表容器 */
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
    font-size: 8.5pt;
    color: #6B7280;
    margin-top: 6pt;
    font-style: italic;
    text-align: center;
}
.chart-number {
    font-weight: 700;
    color: #1B3A6B;
}

/* 分页控制 */
.page-break { page-break-before: always; }
.no-break { page-break-inside: avoid; }

/* 附录区域 */
.appendix {
    border-top: 2px solid #E5E7EB;
    margin-top: 30pt;
    padding-top: 20pt;
}
.appendix h1 {
    color: #6B7280;
    border-bottom-color: #E5E7EB;
    font-size: 14pt;
}

/* 水印(可选) */
.watermark {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(-35deg);
    font-size: 60pt;
    color: rgba(27, 58, 107, 0.04);
    font-weight: 900;
    pointer-events: none;
    z-index: -1;
    white-space: nowrap;
}

------- CSS 结束 -------

【任务二: 重构 build_html_report 函数(核心改动)】

当前 build_html_report 把所有图表统一附在正文末尾。
现在需要改成:图表嵌入对应章节的文字内容之后。

请重新实现 build_html_report 函数:

def build_html_report(
    markdown_content: str,
    title: str,
    chart_figures: list,       # list of plotly Figure 对象(来自 chart_registry)
    chart_captions: list,      # list of str(图表标题)
    generated_date: str = None
) -> str:
    """
    把 Markdown 报告内容 + Plotly 图表 合并成专业排版的 HTML。

    核心逻辑:图表按章节匹配嵌入,不是统一放末尾。

    图表匹配算法:
    ─────────────────────────────────────────────────────────
    1. 把 chart_figures 和 chart_captions 打包成列表:
       charts = list(zip(chart_captions, chart_figures))
       unplaced_charts = list(charts)  # 还未放置的图表

    2. 解析 markdown_content,识别所有二级标题(## 开头的行)
       sections = re.findall(r'^## (.+)$', markdown_content, re.MULTILINE)

    3. 对每个章节标题,在 unplaced_charts 里找最匹配的图表:
       匹配规则(按优先级):
       优先级 1 — 完全包含:图表标题包含章节关键词(忽略大小写和标点)
           例: 章节"地理分布" 匹配 图表"2017年各州订单量分布"
           例: 章节"支付方式" 匹配 图表"支付方式占比饼图"
       优先级 2 — 关键词交集:提取章节和图表标题的2字以上词语取交集
           例: 章节"品类偏好分析" 提取["品类","偏好","分析"]
               图表"Top10品类销售额" 提取["品类","销售额"] → 交集["品类"] → 匹配
       优先级 3 — 无匹配时:该章节不插入图表,图表留到附录

    4. 匹配到的图表从 unplaced_charts 移除(每张图只插入一次)

    5. 没有被匹配到的剩余图表,统一放在"附图"附录区域

    实现要点:
    - 不要逐行解析 Markdown,而是先用 markdown 库转成 HTML
      再用 BeautifulSoup 或 re 在合适位置插入图表 HTML
    - 图表插入点:在每个 <h2> 对应章节的文字内容末尾、下一个 <h2> 之前
    - 图表 HTML 结构:
      <div class="chart-container">
          <img src="data:image/png;base64,{b64}" alt="{caption}"/>
          <p class="chart-caption">
              <span class="chart-number">图{n}</span> {caption}
          </p>
      </div>

    HTML 结构要求:
    ─────────────────────────────────────────────────────────
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>
            /* [上方完整 CSS] */
        </style>
    </head>
    <body>
        <!-- 水印 -->
        <div class="watermark">CONFIDENTIAL</div>

        <!-- running header element(weasyprint 用于页眉) -->
        <div id="page-header">
            <span class="header-title">{title}</span>
            <span class="header-date">{generated_date}</span>
        </div>

        <!-- 封面 -->
        <div class="cover">
            <div class="cover-tag">Analysis Report</div>
            <div class="cover-title">{title}</div>
            <div class="cover-subtitle">AI 数据分析 Agent 自动生成</div>
            <div class="cover-meta">
                <span>生成时间: {generated_date}</span>
                <span>数据来源: Olist Brazilian E-Commerce</span>
            </div>
        </div>

        <!-- 正文(含图表) -->
        {body_with_charts_injected}

        <!-- 未匹配图表的附录(如果有) -->
        {appendix_charts_html}

    </body>
    </html>

    返回: 完整 HTML 字符串
    """
    import re, base64
    from datetime import datetime
    import markdown as md_lib

    if not generated_date:
        generated_date = datetime.now().strftime('%Y年%m月%d日 %H:%M')

    # Step 1: 导出所有图表为 PNG bytes + base64
    chart_data = []
    for i, (caption, fig) in enumerate(zip(chart_captions, chart_figures)):
        png_bytes = export_chart_as_png(fig, width=1100, height=500)
        if png_bytes:
            b64 = base64.b64encode(png_bytes).decode()
            chart_data.append({
                'index': i + 1,
                'caption': caption,
                'b64': b64,
                'placed': False
            })

    # Step 2: Markdown → HTML
    body_html = md_lib.markdown(
        markdown_content,
        extensions=['tables', 'fenced_code', 'nl2br']
    )

    # Step 3: 按章节匹配并插入图表
    # [请实现章节匹配算法,把图表 HTML 插入到对应 <h2> 章节末尾]
    # 提示:可以用 re.split 把 body_html 按 <h2> 分割成多段,
    #       对每段找最匹配的图表,插入后再 join 回去

    # Step 4: 未匹配图表放附录
    unplaced = [c for c in chart_data if not c['placed']]
    appendix_html = ''
    if unplaced:
        appendix_html = '<div class="appendix"><h1>附图</h1>'
        for c in unplaced:
            appendix_html += f'''
            <div class="chart-container">
                <img src="data:image/png;base64,{c['b64']}" alt="{c['caption']}"/>
                <p class="chart-caption">
                    <span class="chart-number">图{c['index']}</span> {c['caption']}
                </p>
            </div>'''
        appendix_html += '</div>'

    # Step 5: 组装完整 HTML
    css = """[上方完整 CSS 内容]"""

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>{css}</style>
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
        </div>
    </div>
    {body_html_with_charts}
    {appendix_html}
</body>
</html>'''

【任务三: 更新 generate_report 函数(tools.py)】

当前 generate_report 读取 chart_registry 的方式需要更新,确保:

1. 读取图表时,过滤掉 fig 为 None 的条目:
   chart_reg = st.session_state.get('chart_registry', [])
   valid_charts = [item for item in chart_reg if item.get('fig') is not None]
   figures  = [item['fig']     for item in valid_charts]
   captions = [item['caption'] for item in valid_charts]

2. 调用 markdown_to_pdf 时传入 figures 和 captions:
   pdf_bytes = report_builder.markdown_to_pdf(
       content, report_title, figures, captions
   )

3. 在 PDF 下载按钮旁边加一行说明文字:
   st.caption(f"📊 本 PDF 包含本轮 {len(figures)} 张图表截图")

【任务四: 更新 export_chart_as_png 函数(report_builder.py)】

当前导出分辨率可能偏低,更新参数默认值:

def export_chart_as_png(fig, width: int = 1100, height: int = 500) -> bytes | None:
    """
    导出分辨率提升到 width=1100, height=500, scale=2
    实际像素: 2200 x 1000,足够 A4 纸高清打印
    """
    try:
        return fig.to_image(format="png", width=width, height=height, scale=2)
    except Exception as e:
        print(f"⚠️ 图表导出失败: {e}")
        return None

【约束】

- CSS 中的字体必须完整保留 fallback 链(微软雅黑 → PingFang SC → STHeiti
  → WenQuanYi → sans-serif),确保在 Windows/Mac/Linux/Streamlit Cloud 全平台
  都能正常渲染中文
- build_html_report 中图表匹配算法:
  * 每张图表只能被放置一次(placed=True 后不再参与匹配)
  * 匹配失败时不报错,图表进入附录
  * 章节无匹配图表时不插入占位符
- export_chart_as_png 失败时必须返回 None,不能抛出异常,
  报告其他部分要继续正常生成
- Word 报告(markdown_to_word)本次不修改
- 所有 report_builder.py 中的函数不能依赖 Streamlit,必须是纯 Python

【交付方式】

严格按以下顺序,每步完成后停下来等我确认再继续:

Step 1: 在 report_builder.py 中替换完整 CSS
        完成后给我一个测试方法:
        "把一段含 h1/h2/表格/列表 的 Markdown 渲染成 HTML,
         用浏览器打开确认样式是否正确(不需要生成 PDF)"

Step 2: 实现 build_html_report 的封面部分和页眉 running element
        仅测试封面页的 HTML 输出,不涉及图表匹配

Step 3: 实现图表匹配算法(章节 → 图表的映射)
        给我一个独立的单元测试:
        传入假设的 sections=["地理分布","品类偏好","支付方式"]
        和 captions=["各州订单量对比","Top品类销售额","支付方式占比"]
        验证匹配结果是否符合预期

Step 4: 把图表 HTML 插入对应章节位置
        完成后生成一份完整 HTML 文件,用浏览器打开检查:
        - 封面页存在
        - 图表出现在对应章节文字之后
        - 未匹配图表出现在附录

Step 5: 用 weasyprint 生成 PDF,检查:
        - 封面独占第一页
        - 页眉在每页显示报告标题
        - 页脚显示页码
        - 图表图片清晰不模糊(如果模糊,调高 scale 参数)
        - 表格未在页面中间断开

Step 6: 更新 tools.py 中的 generate_report(任务三)
        端到端测试:在 Agent 中输入"生成本次分析的完整报告"
        → 下载 PDF → 确认图表出现在对应章节

Step 7: 给我说明以下两个问题的答案:
        (a) 如果本轮对话没有执行过任何 make_chart,
            chart_registry 为空时,PDF 报告的表现是什么?
        (b) 图表匹配算法中,如果两个章节都匹配同一张图表,
            代码是如何处理的?