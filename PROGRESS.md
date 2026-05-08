# AI 数据分析 Agent · 开发进度

---

## ⏳ 待处理 Bug（2026-05-09 记录）

### Bug-1：Word 生成失败（`name 'note_run' is not defined`）

**现象**：点击下载 Word 报告时控制台报 `NameError: name 'note_run' is not defined`，Word 文件无法生成。

**推测根因**：`markdown_to_word` 重构"末尾图表追加"逻辑时，原 `else` 分支（无图表时显示提示语）中的 `note_run` 变量被删除但引用保留，或变量作用域被破坏。

**定位位置**：`src/report_builder.py` → `markdown_to_word()` 末尾 `_word_unplaced` 兜底块。

**优先级**：高（Word 完全不可用）。

---

## 今日完成（2026-05-09）

### Fix：图表导出超时（kaleido 使用系统 Chrome）

**现象**：终端持续输出 `[export_chart_as_png] 超时（>120s），跳过此图表`，PDF / Word 报告中图表全部缺失。

**根因**：kaleido v1.x 首次启动时通过 choreographer **自动下载 Chrome 二进制**，在网络受限环境下下载耗时 >120s，触发超时。系统已安装 Chrome，但代码从未指定路径，导致每次都走下载流程。

**修复（`src/report_builder.py`）**：

| 改动 | 内容 |
|---|---|
| `_find_system_chrome()` | 新增辅助函数，优先在 `C:\Program Files\Google\Chrome\...` 检测系统已安装的 Chrome 路径 |
| `export_chart_as_png` 改用 `kaleido.calc_fig_sync` | 不再走 `fig.to_image()`（触发 choreographer 自动下载），直接调用 kaleido 底层 API 并传入 `kopts={"path": chrome_path}` |
| `_kaleido_major()` | 新增版本检测，自动适配 kaleido v0（`pio.to_image`）/ v1（`calc_fig_sync`）两套 API |
| 超时时间 120s → 30s | 使用系统 Chrome 后单张图表导出 3–5s 完成，30s 完全足够 |

**同步操作**：在 Anaconda 环境执行 `pip install "kaleido>=1.0.0" --user`，升级 kaleido v0.2.1 → v1.3.0（Streamlit 运行在 Anaconda 中，必须在此环境安装）。

**效果**：3 张图表各自 3–5s 内导出成功，PDF / Word 均正常嵌入图表。

---

### Fix + 优化：报告图表与解读文字交替排列

**现象**：PDF / Word 报告中，三段图表解读文字连续输出后，三张图表再集中堆叠——即"解读1 → 解读2 → 解读3 → 图1 → 图2 → 图3"，而非期望的"解读1 → 图1 → 解读2 → 图2 → ..."。

**根因**：`markdown_to_pdf` 的图表注入依赖 `_add_sec_chart()`，该函数仅在遇到下一个 `##` 标题时触发。LLM 生成的图表解读都在同一 `## 三、详细分析` 章节内（用 `###` 子标题区分），导致整章所有图表攒到最后才一起插入。

**修复（`src/report_builder.py`）**：

**PDF（`markdown_to_pdf`）**：
- 新增 `_CHART_LABEL_RE` 正则，匹配 LLM 生成的 `图表1:xxx` / `图1：xxx` 格式行
- 新增 `_inject_chart_inline(caption_hint)`：在当前位置立即注入匹配图表（PNG → reportlab `Image`）
- 解析主循环新增 `_CHART_LABEL_RE` 分支：遇到图表标签行时——① 输出标签文字，② 消费紧跟的 `>` 解读 blockquote（含跨空行探测），③ 立即注入对应图表
- 预计算完成后**重置 `placed` 标记**（预计算只做分组，实际注入时才设置），避免 inline 注入时找不到可用图表
- `_add_sec_chart()` 保留为兜底：跳过已 inline 注入的图表，将未匹配的漏网图表追加到章节末

**Word（`markdown_to_word`）**：
- 新增 `_WORD_CHART_RE` 正则 + `_word_inject_chart(caption_hint)` 函数（按 caption 字符匹配得分选最优图表）
- 同样在解析循环中检测 `图表N:` 行，消费 `>` 解读后立即嵌入图片（`doc.add_picture`）
- 原"末尾统一追加数据图表"逻辑改为：有未匹配漏网图表时才追加到文档末尾

**效果（已验证 PDF）**：

```
图表1:xxx 标签
  图表解读:... （blockquote 缩进灰色）
  [图1 图片]
图表2:xxx 标签
  图表解读:...
  [图2 图片]
图表3:xxx 标签
  图表解读:...
  [图3 图片]
```

---

### 优化：饼图自动切换阈值（>5 → >12）

**位置**：`src/validators.py` `validate_chart_type()`

**改动**：饼图 / 环形图类别数超过阈值自动切换为横向条形图，阈值从 `>5` 放宽至 `>12`，与业界标准对齐（12 个切片以内饼图可读性尚可）。

---

### 依赖更新

| 包 | 变更 |
|---|---|
| `reportlab` | 新增到 `requirements.txt`（PDF 生成必需，之前漏写）|
| `kaleido` | Anaconda 环境 `pip install "kaleido>=1.0.0" --user` 升级至 v1.3.0 |

---

## 今日完成（2026-05-08）— 第二批

### BugFix：PDF 生成无限挂起（7分钟以上）

**现象**：生成 Word + PDF 后，界面卡在"正在生成报告，请稍候..."超过 7 分钟，无任何错误输出，进程不结束。

**根因（三层叠加）**：

| # | 位置 | 问题 |
|---|---|---|
| 1（主因）| `src/report_builder.py` `_add_sec_chart()` 第 1002 行 | 若预导出 PNG 为 `None`（超时），会回退调用 `export_chart_as_png(c['fig'])` —— 这是**无超时保护的同步 kaleido 调用**，Windows 下 kaleido subprocess 在嵌套线程上下文中会无限挂起 |
| 2（同源）| `src/report_builder.py` 附录循环第 1139 行 | 与 1 相同的无超时 fallback 调用 |
| 3（加剧）| `src/tools.py` `generate_report` | `markdown_to_pdf` 通过 `_doc_pool` ThreadPoolExecutor 调用，形成三层嵌套（Streamlit → `_doc_pool` → kaleido 子进程），Windows 下子进程创建死锁 |

**修复（`src/report_builder.py` + `src/tools.py`）**：

| 改动 | 内容 |
|---|---|
| `export_chart_as_png` 新增硬超时（`src/report_builder.py`）| 用独立线程 + `future.result(timeout=20)` 包裹 `fig.to_image()`；超时返回 `None`，永不阻塞调用方 |
| 移除 `markdown_to_pdf` 内部 fallback kaleido 调用 | `_add_sec_chart()` 和附录循环均改为 `png = c.get('png')`，PNG 为 `None` 时直接跳过该图表，不再重新调用 kaleido |
| 移除 `_doc_pool` ThreadPoolExecutor（`src/tools.py`）| `markdown_to_word` / `markdown_to_pdf` 改为直接同步调用（两者均 < 2s），消除三层嵌套；速度不损失，因为耗时的图表预导出已与 LLM 并行完成 |

**效果**：报告生成从无限挂起恢复正常，总耗时 ≤ 2 分钟（LLM ≤90s + 预导出与 LLM 并行 ≈0s 额外等待 + reportlab ≈2s）。

---

### BugFix：多轮对话报告内容串台（核心数据隔离 Bug）

**现象**：第二个问题（物流配送分析）生成的报告，"核心发现""详细分析""数据摘要"等章节输出的是第一个问题（RFM 分层分析）的内容，同时出现"你好！我是你的 AI 数据分析助手"等 greeting 消息。

**根因**：`generate_report` 读取 `st.session_state.messages`（全量历史消息）和 `st.session_state.query_results`（全量历史查询）+ `chart_registry`（全量历史图表），没有"本轮"边界概念，导致所有历史轮次内容被错误合并到当前报告。

**修复（`src/tools.py`）—— 三层轮次隔离**：

| 数据类型 | 隔离机制 |
|---|---|
| **对话消息** | `_report_msg_round_start`：记录上次报告结束时的 `messages` 长度，下次取 `messages[idx:]` |
| **查询数据** | `_round_query_intents`（列表）：`query_database` 每次调用时将 `intent` key 追加进来；`generate_report` 只取此列表内的 `query_results` |
| **图表** | `_report_chart_round_start`：记录上次报告结束时的 `chart_registry` 长度，下次取 `chart_registry[idx:]` |
| **轮次推进** | `generate_report` 完成后：三个指针同步更新，`_round_query_intents` 清空，下轮重新积累 |

边界处理：首次报告（从未设置轮次）fallback 取全部已有 key；有轮次记录但本轮无查询时，`query_results` 为空（不回退到历史数据）。

---

### 优化：报告内容质量提升

**优化1 — Agent 分析洞察充分融入报告**

- 对话摘要字符限制 800 → **1500**，消息数量上限 8 → **12** 条
- 新增 greeting/系统消息过滤：不含分析关键词（数据/分析/排名/占比/率/建议等）的 assistant 消息自动跳过，避免"你好！我是你的 AI 数据分析助手"等干扰内容污染报告
- LLM prompt 强化：明确要求"深度整合 Agent 洞察（原因分析、特殊规律、业务解读），不要简单重复数字，要提炼 Agent 的解读结论"

**优化2 — 图表在报告对应章节附带解读**

- LLM prompt 新增图表清单块：列出本轮所有图表标题，要求"每张图表对应章节须包含 2-4 句视觉洞察解读（描述关键趋势/异常/结论），聚焦图表独有的视觉信息而非重复表格数字"
- 轮次隔离后确保报告只嵌入本轮图表（气泡图只出现在物流报告，RFM 图表只出现在 RFM 报告）

---

## 今日完成（2026-05-08）— 第一批

### PDF 四大专项优化

#### 优化一：生成速度（5分钟 → ~30秒）

**根因**：原流程串行：LLM（max 90s）→ 预导出图表（串行 25s/张）→ Word（max 30s）→ PDF（max 120s）= 最坏 4~5 分钟。

**修复（`src/tools.py`）**：
1. **LLM + 图表预导出并行**：两者互不依赖，用独立 `ThreadPoolExecutor` 同时启动；kaleido 1.x 速度极快（3 张图约 2.5s 并行完成），LLM 结果一到立即构建文档
2. **Word + PDF 并行**：两者都依赖 LLM 输出，但互不依赖，改为同时提交到线程池，分别最多等 30s / 60s
3. **移除旧 120s PDF 超时**：reportlab 实际 < 1s，60s 完全足够
4. **`export_chart_as_png` 去掉内部嵌套线程**：kaleido 1.x 不需要额外线程包裹，直接调用即可（原来的双重嵌套 ThreadPoolExecutor 无意义）

实测时间（本地，3 张图）：约 3s（图表导出 2.5s + reportlab 0.3s）；含 LLM 取决于 DeepSeek API，预计 30-90s 总耗时。

---

#### 优化二：表格列宽自动适配（`src/report_builder.py`）

**根因**：原来 `col_w = avail_w / n_cols` 等宽分配，"总消费金额"、"最大消费金额"等长列内容必然换行。

**修复**：实现 `_compute_col_widths` 逻辑——按每列最大内容长度估算宽度（CJK 字 ≈ 9pt，ASCII ≈ 5pt，+16pt 内边距），按比例分配，最小列宽 14mm，总宽不超版心。效果：所有列宽随内容自适应，彻底消除换行。

---

#### 优化三：金额千位符（`src/report_builder.py`）

**实现**：在 `inline()` 函数前置 `_add_thousands()` 处理：
- 匹配"数字元"模式：126161.70元 → **126,161.70元**
- 匹配大整数（≥4位，含小数）：1750521.46元 → **1,750,521.46元**
- 保护年份（1900-2099 的 4 位整数不加千位符）
- 保护人数等计数（无小数且无"元"后缀不强制格式化）

---

#### 优化四：图表嵌入 PDF（`src/report_builder.py`）

**根因**：章节标题"三、详细分析"与图表标题"RFM用户分层-各层级用户分布"无 bigram 交集，导致所有图表进附录；附录又因 C_BLUE NameError（今日已修）崩溃，图表完全消失。

**修复**：
1. **三级匹配新增 P3 单字兜底**：章节含分析类关键字（析/层/分/趋/比/额/率/布/统/量/增/跌/变）时，可匹配同含这些字的图表——"详细分析（析/分）"成功匹配"RFM用户分层（层/分）"
2. **贪婪匹配**：同一章节一次性吸纳所有能匹配的图表（原来只取第一个）；RFM 场景中"详细分析"章节现在能吸纳全部 3 张图
3. **宽高比修正**：kaleido 导出改为 960×440（scale=1.5），PDF 内的 Image 高度同步更新为 `avail_w × 440/960`

实测结果：3 张 RFM 图表全部出现在"三、详细分析"正文中，不再需要翻到附录。

---

### BugFix：PDF 生成再次超时（NameError 被误报为"超时"）

**现象**：生成含图表的 PDF 时显示"PDF 生成失败：PDF 生成超时（>120s），建议改用 Word 格式"，实际是代码崩溃而非真正超时。

**根因（三个叠加）**：

| # | 位置 | 问题 |
|---|---|---|
| 1（主因）| `src/report_builder.py` 附录块 | `C_BLUE` 颜色常量从未定义，只有 `C_BDR`；有未匹配图表进附录时触发 `NameError` |
| 2（掩盖）| `src/tools.py` `_run_with_timeout` | `except (_cf.TimeoutError, Exception)` 把真实异常和超时一起吞掉，全都返回 `None`，导致错误信息永远是"超时" |
| 3（潜在阻塞）| `src/tools.py` 预导出块 | 使用 `with ThreadPoolExecutor` 上下文，`__exit__` 调 `shutdown(wait=True)`，若某 future 已超时但底层线程仍在跑，会短暂阻塞主线程 |

**修复（`src/report_builder.py` + `src/tools.py`）**：

| 改动 | 内容 |
|---|---|
| `report_builder.py` 第 1064 行 | `C_BLUE` → `C_BDR`（附录分割线颜色，与其他 HR 保持一致） |
| `_run_with_timeout` 异常处理 | 改为只 `except _cf.TimeoutError: return None`；其他异常原样抛出，让调用方的 `except Exception as e` 显示真实原因 |
| 预导出块 | 改为手动 `_pool = ThreadPoolExecutor(...)` + `_pool.shutdown(wait=False)`，不用 `with` 上下文，避免超时 future 拖住主线程 |

---

## 今日完成（2026-05-06）

### PDF 报告专项优化（PDF报告优化.md 全部任务完成）

来源：`PDF报告优化.md` 四项任务，解决"PDF 样式丑陋"和"图表未嵌入报告"两大问题。

---

#### 任务一：重新设计 CSS（`src/report_builder.py`）

新建模块级常量 `_HTML_REPORT_CSS`，替换原有内联 `<style>`：

| 设计规范 | 值 |
|---|---|
| 主色调（深海蓝） | `#1B3A6B` |
| 强调色（橙色） | `#E87722` |
| 正文颜色 | `#2C2C2C` |
| 字体优先级 | Microsoft YaHei → PingFang SC → STHeiti → WenQuanYi → sans-serif |

CSS 覆盖范围：`@page` A4 规格 + 页眉/页脚、封面（`.cover`/`.cover-tag`/`.cover-title`/`.cover-meta`）、h1/h2/h3 标题层级、表格（深海蓝表头 + 斑马纹行）、图表容器（`.chart-container`/`.chart-caption`）、洞察框/建议框、水印、附录区域。

---

#### 任务二：重构 `build_html_report`（`src/report_builder.py`）

完整重写，核心改动：

**封面与页眉**：
- HTML 结构新增 `<div id="page-header">`（weasyprint running element，每页显示标题 + 日期）
- 封面区块包含 `cover-tag`（橙色 "Analysis Report" 标签）、标题、副标题、元信息

**图表按章节匹配嵌入**（不再统一放末尾）：
- `_match_chart_for_section(section_title, unplaced)` 新增辅助函数
  - 优先级 1：图表标题包含章节关键词（字符串包含，忽略大小写）
  - 优先级 2：**中文 bigram 关键词交集**：`re.findall(r'[一-鿿]+', s)` 提取中文字符串，滑动窗口生成 2 字元组，取章节与图表的交集
  - 优先级 3：无匹配 → 图表进附录
- `_chart_html(n, b64, caption)` 生成标准图表 HTML 片段
- 解析 Markdown → HTML 后，用 `re.split(r'(<h2>.*?</h2>)', body_html)` 按 `<h2>` 分割为多段，逐段查找并插入匹配图表
- 未被匹配的图表统一追加到 `<div class="appendix">` 附录区域

**Bigram 匹配验证**（单元测试）：
```
sections = ["地理分布", "品类偏好", "支付方式"]
captions = ["各州订单量对比", "Top品类销售额", "支付方式占比"]
→ 地理分布 ← 各州订单量对比（优先级2，bigram 无交集 → 优先级1 fallback）
→ 品类偏好 ← Top品类销售额（"品类" bigram 交集匹配）
→ 支付方式 ← 支付方式占比（"支付方式" bigram 交集匹配）
```

---

#### 任务三：更新 `generate_report`（`src/tools.py`）

- 始终从 `chart_registry` 读取图表（移除旧 `embed_charts` 开关限制）：
  ```python
  chart_reg = st.session_state.get("chart_registry", [])
  valid_charts = [item for item in chart_reg if item.get("fig") is not None]
  ```
- PDF 下载按钮旁新增说明：`st.caption(f"📊 本 PDF 包含本轮 {chart_count} 张图表截图")`
- 修复 `_render_report_output`：复合格式（`"word+pdf"`）改为 set 解析，不再用精确字符串匹配

---

#### 任务四：提升 `export_chart_as_png` 分辨率（`src/report_builder.py`）

- 默认参数更新：`width=1100, height=500, scale=2`
- 实际导出像素：**2200 × 1000**，满足 A4 高清打印

---

#### 同步优化：PDF 样式与 HTML 对齐（`markdown_to_pdf` / reportlab）

将 reportlab 生成的 PDF 样式与 HTML CSS 完全对齐：

| 元素 | 旧样式 | 新样式 |
|---|---|---|
| 颜色常量 | `#1a1a2e` / `#4C72B0` | `C_NAVY=#1B3A6B` / `C_ORANGE=#E87722` |
| 封面 | 简单标题 + HR | KeepTogether（橙色 badge + 24pt 深海蓝标题 + 副标题 + 元数据 + 粗 HR）+ PageBreak |
| H2 | 普通段落样式 | `_h2_flowable()`：`Table + LINEBEFORE(4pt, C_ORANGE)` 模拟 CSS `border-left` |
| 表头 | 浅蓝背景 | `C_NAVY` 背景 + 白色文字 + 仅底部网格线 |

---

### BugFix：PDF 生成超时（>60s）

**现象**：生成包含图表的 PDF 报告时提示"PDF 生成失败：PDF 生成超时（>60s），建议改用 Word 格式"。

**根因**：`markdown_to_pdf` 内部的 `_add_sec_chart()` 和附录循环**串行**调用 `export_chart_as_png()`（每次最多 25s），3 张图 × 25s = 75s > PDF 超时上限 60s，必然超时。

**修复（`src/report_builder.py` + `src/tools.py`）**：

| 改动 | 内容 |
|---|---|
| `markdown_to_pdf` 新增 `chart_png_bytes` 参数 | 接收预导出的 PNG bytes 列表；`_pdf_charts` 字典增加 `'png'` 字段存储对应 bytes |
| `_add_sec_chart()` 优先用已有 bytes | `png = c.get('png') or export_chart_as_png(c['fig'])`，有预导出结果时直接跳过耗时导出 |
| 附录循环同步修改 | `_png = _c.get('png') or export_chart_as_png(_c['fig'])` |
| `generate_report` 并行预导出 PNG | 在 60s 计时器**开始前**，用 `ThreadPoolExecutor(max_workers=4)` 并行导出所有图表（每张 28s 上限同时跑），再将 bytes 传入 `markdown_to_pdf` |
| PDF 超时上限 60s → 120s | 兜底：应对并行导出本身较慢的场景 |

**效果**：原来 N 张图串行耗时 `N × 25s`，现改为并行 `max(单张耗时) ≤ 28s`，3 张图从最坏 75s 压缩到 ≤28s。

---

## 今日完成（2026-05-05）

### Week 3 · Day 22（下）：主动洞察 + 报告生成系统

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 1742–2140 行**

#### 新建文件

**`src/report_builder.py`**

纯 Python 报告构建模块（不依赖 Streamlit）：

| 函数 | 作用 |
|---|---|
| `markdown_to_word(content, title)` | Markdown → 格式化 Word (.docx)：标题/正文/加粗/表格/项目符号/水平线，含页眉页脚页码 |
| `export_chart_as_png(fig, w, h)` | Plotly Figure → PNG bytes（kaleido）；找不到 kaleido 返回 None，不阻断 |
| `build_html_report(content, title, figs, captions)` | Markdown + 图表截图 → 完整 HTML 字符串（A4 CSS，含中文字体、表格、代码块样式）|
| `html_to_pdf(html)` | HTML → PDF bytes（weasyprint）；找不到 weasyprint 抛 ImportError 给调用方 |
| `markdown_to_pdf(content, title, figs, captions)` | 对外唯一 PDF 入口，依次调 build_html_report + html_to_pdf |

#### 修改文件

**`src/agent.py`**

- 工具列表新增第 5 项 `generate_report`
- `AGENT_SYSTEM_PROMPT` 新增【主动洞察】章节：每轮分析结束后强制推荐 3 个下钻方向，固定格式 `[1]/[2]/[3]`，优先推荐异常点和有业务价值的方向，不重复上一轮已分析的维度

**`src/tools.py`**

- `import report_builder`
- `TOOLS_SCHEMA` 新增 `generate_report` 工具（Schema）：支持 markdown/word/pdf/all 四种格式，audience（management/operation/technical），embed_charts 开关
- `make_chart` section 6 之后新增 `chart_registry` 注册：每次成功生成 Plotly 图表后把 `{fig, caption, timestamp}` 存入 `session_state['chart_registry']`，供 `generate_report` 收集截图
- 新增 `generate_report()` 函数：6 步流程（收集对话历史 + 查询摘要 → LLM 生成 Markdown → Word 生成 → PDF 生成 → 存入 `_report_output` → 返回状态摘要给 LLM）
- `execute_tool()` 新增 `generate_report` 路由

**`src/app.py`**

- `init_session_state()` 新增 `chart_registry = []` 和 `_report_output = []`
- 清空对话按钮同步清空 `chart_registry` 和 `_report_output`
- `_run_and_store_agent()` 每轮开始前清空 `_report_output`，结束时收集后存入 message 的 `report_outputs` 字段
- 新增 `_render_report_output(rpt)` 函数：渲染 Markdown（expander）+ Word 下载按钮 + PDF 下载按钮（失败时显示安装提示）
- `_render_message()` 图表渲染循环之后调用 `_render_report_output`

#### 新增依赖

```
pip install python-docx markdown kaleido
```

weasyprint（PDF）为可选依赖，Windows 需额外安装 GTK 运行时；未装时 UI 显示友好提示而非崩溃。

#### 用户说"PDF 未安装 weasyprint"时的提示

界面上会显示黄色警告框：
> ⚠️ PDF 生成需要 weasyprint。安装方法：`pip install weasyprint`
> Windows 用户还需安装 GTK 运行时，详见 weasyprint 官方文档。
> 可以使用 Word 格式作为替代。

Word 下载按钮仍然可用（python-docx 不依赖 GTK）。

---

## 今日完成（2026-05-04）

### Week 3 · Day 21：归因诊断工具接入 Agent（Day 21 手册任务）

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 1690–1724 行**

#### 修改文件

**`src/agent.py`**

- `AGENT_SYSTEM_PROMPT` 的 `【diagnose_metric 使用规则】` 段落扩充两块内容：
  1. **调用前确认清单**：触发时机明确为"为什么X变了/X下跌的原因"；调工具前须在心里核实三点：指标定义（销售额是否含运费）、对比时期（A期/B期）、下钻维度（最多4个）
  2. **输出格式 5 条强制要求**：
     - 总体变化量（绝对值 + 百分比）
     - Top 3 贡献因素（变化量 + 贡献度%）
     - 置信度评估（直接引用工具返回值，不得自行修改）
     - 局限性说明（未建模的外部因素）
     - 建议下一步动作（具体可执行）

#### 当前状态

归因诊断功能（Day 18-21）已全部完成：

| 阶段 | 内容 |
|---|---|
| Day 18（validators + Schema） | `TIME_FILTER_TEMPLATES`、`validate_diagnose_params`、`diagnose_metric` 工具 Schema |
| Day 19-20（核心实现） | SQL 拼接、贡献度计算、LLM 结论生成、置信度评估，共 6 个函数 |
| Day 21（接入 Agent） | System Prompt 触发规则 + 确认清单 + 输出格式 5 项要求 |

---

### BugFix：Rule 6 隐式过滤——LLM 自加数量阈值过滤

**现象**：用户问"各品类平均价格、平均评分和订单量三者的关系"，LLM 自行在 SQL 中加了 `WHERE order_count >= 10`（注释写"过滤订单量太少的品类，使气泡图更有意义"），导致第一次查询返回 70 条，后续追问变为 73 条，数据前后不一致。

**根因**：Rule 6 只列举了 `order_status != 'canceled'` 作为反例，未覆盖"以提升图表质量为由"的数量阈值过滤。

**修复（`src/agent.py` + `src/prompts.py`）**：

- `agent.py` Rule 6 新增：严禁以"提升图表质量/数据太少没意义"为由自加数量阈值过滤（`order_count >= N`、`HAVING COUNT(*) > N`），且 SQL 注释里的合理性解释不构成豁免
- `prompts.py` Rule 6 新增同类反例：`WHERE order_count >= 10`，并附具体注释场景

---

### BugFix：气泡图 KeyError（`AGENT_SYSTEM_PROMPT.format()` 花括号未转义）

**现象**：添加气泡图功能后，Agent 启动即报 `KeyError: '"size_col"'`，发生在 `agent.py` 第 363 行 `AGENT_SYSTEM_PROMPT.format(schema_text=schema_text)`。

**根因**：气泡图示例中的 `{"size_col": "order_count", "label_col": "category"}` 包含花括号，被 Python `.format()` 当作占位符解析。

**修复（`src/agent.py`）**：将示例中的 `{...}` 改为 `{{...}}`（format 转义写法），LLM 看到的内容不变。

---

### Week 3 · Day 22：气泡图（bubble）

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 1289–1424 行**

#### 修改文件

**`src/tools.py`**

- `make_chart` 函数签名新增 `bubble_options: dict = None`
- 绘图 section 4 新增 `elif final_type == "bubble"` 分支：
  - 从 `bubble_options` 读取 `size_col / label_col / size_max / color_col`
  - 参数校验：`size_col` 缺失或字段不存在 → 直接返回错误
  - 数值校验：`size_col` 含非正数 → 自动偏移（不报错）+ 追加 warning
  - `hover_data`：X/Y 轴显示 2 位小数，size_col 显示千位符
  - `px.scatter(size=size_col)` 绘制气泡图
  - `add_vline / add_hline`：中位数参考线（必须显示）
  - 象限统计 `_bubble_quadrant_counts`：四象限数据点计数，存入 chart dict
- 布局 section 5：新增 `elif final_type == "bubble"` 分支，对 X、Y 双轴应用 `_apply_tick_format`
- 存储 section 6：气泡图额外写入 `chart_kind="bubble"` 和 `quadrant_counts`
- `execute_tool`：透传 `bubble_options=args.get("bubble_options")`

**`src/validators.py`**

- `validate_chart_type` 新增规则 5（气泡图）：
  - X/Y 轴为非数值列 → 降级为 bar + 警告
  - 数据量 < 3 → 降级为 table + 警告
  - 数据量 > 200 → 保留 bubble，只显示建议过滤的提示
- 原规则 5（y_cols 多系列）顺延为规则 6

**`src/agent.py`**

- `AGENT_SYSTEM_PROMPT` 图表选择规则新增气泡图条目：
  - 选择条件：三个数值维度 + 大小语义字段 + 数据点 5-100 个
  - 调用要求：必须填 `bubble_options.size_col`，建议填 `label_col`
  - 典型触发词："三维分析"/"气泡"/"大小表示"
  - 附完整参数示例

**`src/app.py`**

- `_render_message()` 新增 `elif chart_kind == "bubble"` 分支：
  - 渲染 Plotly 气泡图
  - 渲染象限分布 expander（"📊 象限分布统计"，显示各象限数据点数 + 占比）

#### 测试用例（手册）

```
"用气泡图分析各品类的平均价格、平均评分和订单量的关系"
→ X 轴: avg_price，Y 轴: avg_score，气泡大小: order_count
→ 中位数参考线划分四象限，悬停显示品类名称
```

---

### Week 3 · Day 21（下）：词云图（wordcloud）

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 858–994 行**

#### 新建文件

**`src/chart_utils.py`**

- **`get_font_path()`**：自动检测中文字体，优先级：项目内置 `assets/fonts/SimHei.ttf` → 系统字体（Windows msyh/simhei / Mac STHeiti / Linux wqy）→ None（降级，打印警告）
- **`render_wordcloud(df, text_col, word_col, freq_col, title, colormap, max_words, language)`**：
  - 两种输入模式：已分词（word_col+freq_col）或原始文本（text_col）
  - 中文停用词过滤（60+ 个常用停用词）
  - 语言自动检测：auto 模式通过 Unicode 范围判断是否含中文
  - jieba 分词（中文），缺 jieba 时自动降级为标点切分并打印警告
  - max_words 上限 200，超出自动截断
  - matplotlib Agg 后端渲染，不弹 GUI 窗口
  - 输出 PNG bytes（150 dpi），不依赖 Streamlit

**`test_wordcloud.py`**

- `test_word_freq_mode()`：10 个品类 + 订单量的 DataFrame，测试 word_col+freq_col 模式
- `test_text_col_mode()`：英文评论文本，测试 text_col 模式
- 两项测试均通过（208 KB + 255 KB PNG）

#### 修改文件

**`src/validators.py`**

- 新增 `validate_wordcloud_input(df, wc_opts)`：
  - 检查 text_col 或 (word_col + freq_col) 至少提供一组
  - text_col 列存在性 + 全空检查
  - freq_col 数值类型检查
  - 有效行数 < 5 时返回警告（不阻断生成）

**`src/tools.py`**

- 导入 `chart_utils` 和 `validate_wordcloud_input`
- `TOOLS_SCHEMA make_chart`：
  - `chart_type` enum 新增 `"wordcloud"`
  - `x_col` 描述更新（词云不需要）
  - 新增 `wordcloud_options` 参数（含 text_col/word_col/freq_col/colormap/max_words/language）
  - `required` 移除 `x_col`（词云和非词云都兼容）
- `make_chart` 函数签名新增 `wordcloud_options: dict = None`，`x_col` 改为可选
- 词云图早出分支（在 x_col/y_col 校验之前检测 `chart_type == "wordcloud"`）：
  - 调 `validate_wordcloud_input` → 调 `chart_utils.render_wordcloud`
  - 存入 `_agent_charts` 字典：含 `chart_kind="wordcloud"` + `png_bytes`
- `execute_tool` 透传 `wordcloud_options`

**`src/app.py`**

- `_render_message()` 图表循环改为 `enumerate`（获取索引用于 download_button key 去重）
- 检测 `chart_kind == "wordcloud"`：`st.image(png_bytes)` + `st.download_button` 下载 PNG
- `chart_kind` 不存在时回退为 plotly 渲染（向后兼容）

**`src/agent.py`**

- 图表选择规则新增 wordcloud 条目：已聚合数据用 word_col+freq_col，原始文本用 text_col

#### 新增依赖

```
pip install wordcloud matplotlib
```

---

### Week 3 · Day 21（上）：图表类型用户需求优先

#### 需求背景

用户希望绘图时自己有最终决定权：明确指定了图表类型则优先使用，LLM 认为不合理时**同时返回两张图**供选择，而非静默降级。

#### 改动设计

| 场景 | 旧行为 | 新行为 |
|---|---|---|
| 用户指定合理图表类型 | LLM 自行选择（可能忽略用户意图） | 强制使用用户指定类型 |
| 用户指定不合理类型（如 pie 画 20 类） | 自动降级为 barh，显示警告 | 返回两张图：**📌 你要求的图表** + **💡 AI 推荐图表** |
| 用户未指定类型 | LLM 自行选择 | 同旧行为，无变化 |

#### 修改文件

**`src/tools.py`**

- `make_chart` Schema 的 `description` 新增三条图表类型优先级规则说明
- Schema 新增 `force_chart_type` 参数（boolean）：true 时跳过 `validate_chart_type`，强制使用用户指定类型
- Schema 新增 `chart_source` 参数（enum: normal/user_requested/ai_recommended）：标记图表来源
- `make_chart` 函数签名新增 `force_chart_type: bool = False` 和 `chart_source: str = "normal"`
- Step 2 改为：`force_chart_type=True` 时直接 `final_type=chart_type, warning=None`，跳过校验
- `_agent_charts` 存储字典新增 `chart_source` 字段
- `execute_tool` 透传两个新参数

**`src/agent.py`**

- `AGENT_SYSTEM_PROMPT` 在图表选择规则前新增【图表类型用户需求优先规则】章节：
  - 情况 A（用户要求合理）：force_chart_type=true + chart_source="user_requested"，只调一次
  - 情况 B（用户要求不合理）：先调一次 force=true（user_requested），再调一次推荐类型（ai_recommended），文字说明两图的区别
  - 情况 C（用户未指定）：正常流程，chart_source="normal"

**`src/app.py`**

- `_render_message()` 图表渲染循环新增 `chart_source` 读取
- `user_requested` 时在图表上方显示 `📌 你要求的图表`
- `ai_recommended` 时显示 `💡 AI 推荐图表（数据更适合此类型）`
- `normal` 时不显示标签（兼容旧行为）

---

## 今日完成（2026-05-03 晚）

### Week 3 · Day 18-20：归因诊断工具 `diagnose_metric`

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 835–994 行**

#### 新增功能

**`diagnose_metric` 工具**：将"为什么 X 指标变了"这一最高频分析需求工程化。输入两个时间段和下钻维度，自动完成 SQL 拼接、贡献度计算、置信度评估，并调用 LLM 生成中文归因结论。

---

#### Day 18：时间模板层 + 工具 Schema

**`src/prompts.py`**

- 新增常量 `TIME_FILTER_TEMPLATES`（5 种模板：month_range / quarter / year / last_n_days / custom）
- 每条含 description / template / example，供 LLM few-shot 参考；diagnose_metric Schema 的 description 中内联了完整示例

**`src/validators.py`**

- 新增 `import re`
- 新增常量 `_DANGEROUS_KEYWORDS`（INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE/EXEC/EXECUTE）
- 新增 `validate_diagnose_params(base_sql, period_a, period_b, drill_dimensions) -> tuple[bool, str]`：
  - 检查 base_sql / filter_sql 不含危险关键字
  - 检查 base_sql 含 SELECT 和 FROM
  - 检查 period_a/b 的 filter_sql / label 非空
  - 检查 drill_dimensions 非空且各项有 dimension_name / dimension_col

**`src/tools.py`**（Schema 部分）

- 新增 imports：`re`、`OpenAI`、`DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / MODEL_NAME`、`validate_diagnose_params`
- `TOOLS_SCHEMA` 追加第 4 个工具 `diagnose_metric`：
  - 必填参数：metric_name / base_sql / date_column / period_a / period_b / drill_dimensions
  - 可选参数：decomposition_formula（指标分解公式，如"销售额 = 订单数 × 客单价"）
  - description 内联时间过滤 few-shot 示例

---

#### Day 19-20：核心实现

**`src/tools.py`**（函数实现部分）

| 函数 | 作用 |
|---|---|
| `_split_base_sql(base_sql)` | 正则拆分 SELECT 聚合表达式 + FROM 子句 |
| `_run_sql(sql, ds)` | 执行 SQL，返回 (首数值列值, DataFrame) |
| `_run_dim_sql(sql, ds)` | 容错版维度 SQL 执行，失败返回空 DataFrame |
| `_call_llm_for_conclusion(...)` | 调 DeepSeek 生成 3-5 句中文归因结论 |
| `_assess_confidence(change_pct, top_contribution_pct, period_a_value)` | 规则评估置信度（高/中/低）+ 局限性列表 |
| `diagnose_metric(...)` | 主函数，6 步完成完整归因分析 |

`diagnose_metric` 执行逻辑（6 步）：

1. **参数校验**：调 `validate_diagnose_params`，失败立即返回错误，不执行 SQL
2. **总体变化**：拼接 `{base_sql} WHERE {filter_sql}` 查两期指标值，计算绝对/相对变化
3. **维度下钻**：对每个 drill_dimension：
   - 构造带 GROUP BY 的 SQL（支持 extra_join），自动追加品类 NULL 过滤
   - 分别查 A/B 期数据，outer merge，计算每个维度值的 `contribution_pct`
   - `contribution_pct = (val_b - val_a) / |total_change| × 100`
   - 按贡献度绝对值降序排列，取 Top 10
4. **汇总 Top 贡献因素**：跨所有维度合并，取 Top 5，按贡献度绝对值排序
5. **LLM 结论**：把总体变化 + Top 5 贡献因素传给 DeepSeek，生成中文归因段落
6. **存储 & 返回**：结构化结果存入 `session_state['_diagnose_results']`，返回格式化文本摘要

置信度评估规则（纯代码，不用 LLM 自评）：
- **高**：总变化 > 10% 且 Top 贡献因素占比 > 40%
- **中**：总变化 5-10%，或 Top 贡献 20-40%
- **低**：总变化 < 5%（可能是正常波动）或 Top 贡献 < 20%

**`src/agent.py`**

- system prompt 工具列表新增 `diagnose_metric` 条目（含适用场景说明）
- 新增【diagnose_metric 使用规则】章节：base_sql 格式、filter_sql 标准写法、品类维度 extra_join 固定写法

---

#### 修改文件汇总

| 文件 | 变更内容 |
|---|---|
| `src/prompts.py` | 新增 `TIME_FILTER_TEMPLATES` 常量（5 种时间过滤模板） |
| `src/validators.py` | 新增 `validate_diagnose_params()`（SQL 安全检查 + 参数完整性校验） |
| `src/tools.py` | 新增 imports；TOOLS_SCHEMA 追加 `diagnose_metric`；新增 5 个私有辅助函数 + `diagnose_metric()` 主函数；`execute_tool()` 加入 `diagnose_metric` 路由 |
| `src/agent.py` | system prompt 新增工具 4 说明 + 【diagnose_metric 使用规则】章节 |

---

## 当前停在

**Week 3 · Day 22 全部完成（2026-05-05）— Week 3 已收官**

当前 Agent 具备的能力：
- **防幻觉**：`query_database` ≤100 行全量传给 LLM
- **SQL 防护**：12 条规则（Fan-out、NULL 品类、同比/环比、跨年边界、禁止自加数量阈值过滤等）
- **多步规划**：先输出分析计划，逐步调用工具
- **多轮记忆**：`_trim_messages` 确保不超 token 限制
- **智能图表**：12 种图表类型 + 自动校验降级 + insight + 原始数据 expander
- **多系列图表**：bar/barh/line 支持 y_cols（宽格式）和 color_col（长格式）
- **词云图**：wordcloud，支持已聚合和原始文本两种模式
- **气泡图**：bubble，中位数参考线 + 四象限统计 + 双轴 k/M/G 格式化
- **归因诊断**：`diagnose_metric` 全链路（SQL 拼接 + 贡献度计算 + 置信度评估 + LLM 结论）
- **主动洞察**：每轮分析后自动推荐 3 个下钻方向，引用具体数字，不重复已分析维度
- **报告生成**：`generate_report` 工具，支持 Markdown 展示 + Word 下载 + PDF 下载（含图表截图）

下次工作建议（Week 4 方向）：
1. **归因诊断可视化**：用 Plotly 瀑布图渲染 `_diagnose_results` 贡献度
2. **图表交互优化**：下钻筛选、导出 PNG/CSV
3. **多数据源支持**：用户上传 CSV/Excel 后可直接查询
4. **weasyprint 安装测试**：验证 PDF 完整管线（含图表截图嵌入）

---

## 今日完成（2026-05-03 下午）

### Week 3 · Day 18：图表系统 BugFix + 多系列图表能力

本次工作以实际提问测试 Agent 图表输出质量为驱动，修复 8 个图表 Bug，并新增多系列图表能力。

---

#### BugFix 1：barh 横纵轴对调（轴标题与数据单位相反）

**现象**：barh 图 Y 轴标题显示"州"但值是数字，X 轴标题显示"订单量"但值是州名。

**根因**：`make_chart` 工具描述中 `y_col` 写的是"主指标"，LLM 把度量列给了 y_col；而 Plotly `px.bar(orientation='h')` 约定 x=度量、y=分类，导致轴对调。

**修复（`src/tools.py`）**：
- 工具描述明确：**barh 时 x_col 填度量列、y_col 填分类列**
- barh 绘图路径加防御逻辑：若检测到 x_col 是字符串列、y_col 是数值列，**自动对调**

---

#### BugFix 2：图表数值无 k/M/G 单位，小数位不受控

**现象**：轴刻度显示原始数值（如 41746），无单位缩写，部分浮点数小数位过多。

**修复（`src/tools.py`）**：
- 添加常量 `_TICK_FMT_STOPS`（Plotly `tickformatstops`）：步长 < 1k 保留 2 位小数、1k-1M 用 k、1M-1B 用 M、≥1B 用 G
- 添加 `_apply_tick_format(fig, axes)` 工具函数，统一应用到所有图表数值轴
- 移除旧的「万单位缩放」逻辑（数据不再 ÷10000），改为纯显示层格式化

---

#### BugFix 3：combo 双轴图右轴标题为英文列名

**现象**：右侧 Y 轴标题显示 `total_amount`（原始列名），应显示中文。

**修复（`src/tools.py`）**：
- Schema 新增 `y_axis_label_2` 参数（中文右轴标题，仅 combo 使用）
- `make_chart` 函数签名和 `execute_tool` 同步更新
- combo 绘图代码改为 `y_axis_label_2 or y_col_2`

---

#### BugFix 4：同比/环比计算混用（环比 SQL 实为同比逻辑）

**现象**：用户问"环比"，Agent 生成 `LAG(val, 12)` 跨年比较，实为同比。

**修复（`src/agent.py` SQL 规则 11）**：
- 明确定义：**环比 = LAG(val, 1)（紧邻上一期）**；**同比 = LAG(val, 12/4)（上一年同期）**
- 严禁把环比写成跨年 LAG

---

#### BugFix 5：heatmap 颜色列使用第一个非 x/y 列，而非目标指标列

**现象**：要求热力图展示环比率，但颜色却按 `total_amount` 渲染（第一个非 x/y 列），因为代码硬写了 `other_cols[0]`。

**修复（`src/tools.py`）**：
- heatmap 绘图路径改为**优先使用 `color_col`**，未提供时才 fallback 到 `other_cols[0]`
- `color_col` schema 描述明确：**heatmap 必填，指定哪列决定格子颜色**
- `agent.py` 图表规则补充 **heatmap 专项规则**：必须设置 `color_col`

---

#### BugFix 6：heatmap 含负值但使用蓝色单色板

**修复（`src/tools.py`）**：
- 自动检测 z 列是否含负值，含负值改用 `RdYlGn`（红绿双色，0 为黄色中间）
- 格子内显示数值（`text_auto=".1f"`）

---

#### BugFix 7：heatmap 极端异常值劫持色阶（全图两色）

**现象**：PR 州 1 月环比 +50,235%，色阶上限被拉到 50k，其余所有格子全红。

**修复（`src/tools.py`）**：
- 使用 **5th/95th 百分位截断**设定 `zmin/zmax`
- 含负值时：取 q5/q95 绝对值较大者作边界，色阶从 `-bound` 到 `+bound`（0 居中）
- 大多数格子充分展示颜色差异，极端值仍显示为极端色

---

#### BugFix 8：环比计算 1 月显示 None（跨年边界数据缺失）

**现象**：计算 2017 年月度环比，1 月 `prev_month_amount` 为 None，因为 SQL `WHERE year=2017` 导致 LAG(1) 在月份=1 时找不到上一期。

**修复（`src/agent.py` SQL 规则 12）**：
- 新增「**跨年边界**」规则：环比/同比计算必须在 CTE 里多拉一个前置期（2016-12），计算完 LAG 后外层再 WHERE 过滤回目标年份
- 附完整 SQL 示例供 LLM 参照

---

#### 新功能：多系列图表（bar / barh / line）

**背景**：原图表只支持单列 `y_col`，无法展示"各季度各州订单对比"等多系列需求。

**交付内容（`src/tools.py` + `src/validators.py` + `src/agent.py`）**：

| 改动点 | 内容 |
|---|---|
| Schema 新增 `y_cols` 参数 | 数组类型，bar/barh/line 宽格式多系列专用；`y_col` 从 required 移除 |
| `y_col` 描述更新 | 明确"单系列时使用，多系列改用 y_cols" |
| 函数签名 | `make_chart` 加 `y_cols: list = None`，`execute_tool` 同步传参 |
| 多系列分发逻辑 | `is_multi = bool(y_cols)`，bar/barh/line 各加 `if is_multi` 分支 |
| 3 个私有函数 | `_make_bar_multi`（分组柱）、`_make_barh_multi`（横向分组条）、`_make_line_multi`（多线折线） |
| 字段校验 | y_cols 中不存在的列 / 非数值列均返回明确错误 |
| `validators.py` 规则 5 | >15 系列警告；pie/donut/scatter 传 y_cols → 自动降级为 bar |
| `agent.py` 多系列规则 | 宽格式（多数值列）用 y_cols；长格式（分组字段+数值列）用 color_col；含判断示例 |

**支持的使用模式**：
- 宽格式：`x_col="月份", y_cols=["Q1","Q2","Q3","Q4"]`（SQL 用 PIVOT/CASE WHEN 生成宽表）
- 长格式：`x_col="月份", y_col="销量", color_col="品类"`（GROUP BY 两维度的长表）

---

#### 修改文件汇总

| 文件 | 变更内容 |
|---|---|
| `src/tools.py` | barh 自动纠偏；k/M/G tick 格式化；`y_axis_label_2`；heatmap color_col 优先级 + 百分位色阶 + RdYlGn；`y_cols` 多系列支持；3 个多系列私有函数 |
| `src/validators.py` | 多系列规则 5（系列数、pie/scatter 降级） |
| `src/agent.py` | SQL 规则 11（同比/环比定义）；规则 12（跨年边界）；图表规则补充 heatmap 专项 + 多系列规则 |

---

## 当前停在

**Week 3 · Day 18 完成**

当前图表系统具备的能力：
- **10 种图表类型**：bar / barh / line / area / pie / donut / scatter / heatmap / combo / table
- **多系列图表**：bar / barh / line 支持 `y_cols`（宽格式）和 `color_col`（长格式）两种模式
- **轴格式化**：k/M/G 自动单位，最多 2 位小数，barh / combo 双轴均覆盖
- **barh 纠偏**：LLM 传反列时自动对调，不报错
- **heatmap**：正确指标列着色 + 正负双色 + 百分位鲁棒色阶 + 格子内数值
- **SQL 防护**：12 条规则，含同比/环比区分、跨年边界、NULL 品类、Fan-out 等

下次工作建议（根据手册优先级）：
1. **图表交互优化**：下钻、筛选、导出 PNG/CSV
2. **多数据源支持**：用户自定义上传 CSV/Excel 文件后可直接查询
3. **Agent 能力升级**：支持"帮我写分析报告"等长文本输出

---

## 今日完成（2026-05-03 上午）

### Week 3 · Day 15-17：智能图表系统

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 651–811 行**

#### 新建文件

**`src/validators.py`**

- **`validate_chart_type(chart_type, df, x_col, y_col) -> tuple[str, str | None]`**：
  - 规则1：pie/donut 类别数 > 5 → 自动切换 barh + 警告
  - 规则2：line 的 x_col 无法解析为时间格式 → 切换 bar + 警告
  - 规则3：scatter 的 x 或 y 列不是数值型 → 切换 bar + 警告
  - 规则4：数据只有 1 行 → 不切换，只警告

#### 修改文件

**`src/tools.py`**

- **新增常量 `COLOR_PALETTE`**：10色商业色板（Seaborn deep 系列）
- **`TOOLS_SCHEMA` 中 make_chart 完整重写**：
  - chart_type enum 从 4 种扩展到 10 种（新增 barh / donut / heatmap / area / combo / table）
  - 新增参数：`y_col_2`（combo 第二轴）、`color_col`（多系列着色）、`x_axis_label`、`y_axis_label`、`format_options`（sort_by/limit/auto_format_large）、`insight`（图表解读，必填）
  - required 字段增加：chart_type、x_col、y_col、title、x_axis_label、y_axis_label、insight
- **`_apply_format_options()` 辅助函数**：处理排序/截断/大数值万元化
- **`make_chart()` 全面重写**：
  - 支持所有 10 种图表类型（bar/barh/line/area/pie/donut/scatter/heatmap/combo/table）
  - combo 双轴图用 `make_subplots(secondary_y=True)` 实现
  - heatmap 自动 pivot 为矩阵或降级为密度热力图
  - table 用 `go.Table` 渲染，含斑马纹行色
  - 存入 `_agent_charts` 的结构升级为 `{fig, title, warning, insight, df}`
- **`execute_tool()`**：透传新增参数（y_col_2/color_col/format_options/insight 等）

**`src/app.py`**

- **`_run_and_store_agent()`**：charts 提取从 `[item["fig"] for item in ...]` 改为 `list(...)` 保留完整字典
- **`_render_message()` 图表渲染升级**：
  - 判断 chart 是 dict（新格式）还是 Figure 对象（旧格式，向后兼容）
  - 新格式依次渲染：`st.plotly_chart` → `st.warning`（若有降级警告）→ `st.info`（insight 解读）→ `st.expander("查看原始数据")`

**`src/agent.py`**

- **`AGENT_SYSTEM_PROMPT` 新增【图表选择规则】**：
  禁止 3D 饼图、类别>5用 barh、时间序列用 line、双量级用 combo、不确定用 bar/table、必须填 result_key

#### 测试场景（手册要求）

| 场景 | 预期行为 |
|---|---|
| LLM 尝试 pie 画 20 个品类 | 自动降级为 barh + 显示警告 |
| LLM 用 line 画分类字段（非时间） | 自动降级为 bar + 警告 |
| 正常 bar 图 | 正常显示，无警告，含 insight + 原始数据 expander |
| combo 双轴（订单量+转化率） | 左轴柱状 + 右轴折线，两轴颜色对应 |

---



### Week 2 · Day 14：多轮记忆 + 上下文管理

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 596–623 行**

#### 修改文件

**`src/agent.py`**

- **新增常量** `MAX_CONTEXT_CHARS = 50_000`、`KEEP_ROUNDS = 6`
- **新增 `_trim_messages(messages)` 函数**：
  - 计算 messages 总字符数，超过 50000 时触发截断
  - 始终保留：system message + 最新 6 轮完整对话
  - 对旧轮次：保留 user 消息 + assistant 最终文字回答，删除 tool 消息和 tool_calls 细节（占空间最多）
  - 兼容 messages 中混有 OpenAI `ChatCompletionMessage` 对象（非 dict）的情况
- **在 Agent 主循环每次迭代开头调用** `messages = _trim_messages(messages)`，确保每次 LLM 调用前都不超限
- **`AGENT_SYSTEM_PROMPT` 新增【上下文记忆】章节**，4 条规则：
  1. 理解代词指向（"那"指上一轮主题，直接延续）
  2. 沿用用户自定义术语（如"活跃用户=最近30天有下单"）
  3. 避免重复查询（历史已有的结论直接引用）
  4. 推进分析深度（已看过的维度→推荐下钻）

**`src/app.py`**

- **Sidebar 顶部新增「🗑️ 清空对话」按钮**：
  - 清空 `st.session_state.messages`（重置为初始欢迎语）
  - 清空 `query_results`、`latest_query_key`、`_agent_charts`、`pending`
  - 调用 `st.rerun()` 立即刷新页面

#### 交付标准对应（手册测试场景）

| 对话轮次 | 预期 Agent 行为 |
|---|---|
| 对话 1: `"查一下 2017 年总销售额"` | 正常查询，返回结论 |
| 对话 2: `"那分到各个州看呢？"` | 理解"那"→ 2017 年销售额，按州分组查询，不重新发问 |
| 对话 3: `"Top 5 的州具体是哪些？"` | 延续上轮结果，直接筛选 Top 5，三轮上下文连贯 |

---

## 历史阶段总结（截至 2026-05-03 上午，Week 3 Day 15-17 完成）

当前 Agent 具备的能力总结：
- **防幻觉**：`query_database` 返回 ≤100 行全量数据，禁止 LLM 在结果外补充
- **SQL 防护**：10 条规则（Fan-out、NULL 品类、隐式过滤、自造标签等）
- **多步规划**：先输出分析计划，逐步调用工具，每步说明发现
- **多轮记忆**：对话历史传给 LLM，`_trim_messages` 确保不超 token 限制
- **智能图表**：10 种图表类型 + 自动校验降级 + insight 解读 + 原始数据 expander

手册进度：`AI数据分析Agent_完整开发手册_v2.md` 第 811 行（Day 17 结束）。

---

## 历史记录（2026-05-02）

### 数据一致性深度排查 · Prompt 防护体系完善（无手册对应，超出计划的自主 QA）

本次工作以实际提问测试 Agent 输出质量为驱动，发现并修复了 5 个层叠 bug，最终建立了一套防止 LLM 产生幻觉数据的系统性防护规则。

#### 问题背景

以"2017年Q4哪10品类销售额下跌最严重"为测试题，反复与 Agent 输出对比，逐步挖出根因。

---

#### Bug 1：LLM 返回结果只预览 3 行，排名 4-10 靠幻觉填充

**现象**：Agent 输出的 Top 3 正确，第 4-10 名全部是捏造的品类和数字（furniture_decor、garden_tools 等实际上 Q4 是上涨的）。

**根因**：`tools.py` 的 `query_database()` 仅返回 `df.head(3)` 给 LLM。SQL 查出 10 行，LLM 只看到 3 行，对剩余 7 行凭印象填充。

**修复（`src/tools.py`）**：改为**动态截断策略**：
- 结果 ≤ 100 行 → 全量传给 LLM（零幻觉）
- 结果 > 100 行 → 只传前 100 行 + `⚠️` 截断警告，提示 LLM 加 LIMIT

```python
MAX_FULL_ROWS = 100
if len(df) <= MAX_FULL_ROWS:
    data_text = df.to_string(index=False)   # 全量
else:
    data_text = df.head(MAX_FULL_ROWS).to_string(index=False)
    suffix = f"⚠️ 结果共 {len(df)} 行，已截断至前 {MAX_FULL_ROWS} 行..."
```

**配套（`src/agent.py` 工作方式）**：新增【数据完整性】规则，明确 LLM 看到的就是完整数据，禁止在结果之外补充任何行或数字。

---

#### Bug 2：LLM 自行添加 `order_status != 'canceled'` 隐式过滤

**现象**：每个 SQL 都包含 `AND o."order_status" != 'canceled'`，用户从未要求。

**根因**：违反 System Prompt 规则 6（禁止隐式过滤），LLM 自以为"分析销售额当然要排除取消订单"。

**修复**：
- `src/agent.py` 规则 6 补充：**严禁自行加 `order_status != 'canceled'`**，未经要求必须查全量
- `src/prompts.py` 规则 6 补充反例

---

#### Bug 3：products 表有 610 个产品无品类（NULL），混入品类排名

**现象**：排名中出现 `None（未分类）`，环比跌幅 -100%，跌幅金额 -14,272，占据一个席位挤掉真实品类。

**根因**：`products.product_category_name` 有 610 条 NULL，`COALESCE(t.english, p.name)` 结果仍为 NULL，被 pandas 渲染为 `"None"` 并混入排名。

**隐藏的次生 Bug**：FULL OUTER JOIN 中 `NULL = NULL` 在 SQL 里判为 **False**，导致 Q3 和 Q4 的 NULL 品类行无法配对：Q3 NULL 行独立显示为 Q4=0（实际 Q4 有 49,141 销售额），虚假跌幅 -100%。

**修复（`src/agent.py` 规则 10 + `src/prompts.py` 规则 13）**：品类分析 SQL 必须在每个 CTE 加：
```sql
WHERE p."product_category_name" IS NOT NULL
```

---

#### Bug 4：品类自造标签（CASE WHEN / LIKE 合并多个葡文品类）

**现象**：fashio_female_clothing 的 Q3 销售额从正确的 855 虚增到 6,758（约 8 倍）。

**根因**：LLM 用 `CASE WHEN product_category_name LIKE '%roupa%'` 创造了假标签 `'fashio_feminine'`，把女装、男装、童装等多个葡文品类错误合并。

**修复**（已在前次对话中实施）：
- `src/agent.py` 规则 9：必须 JOIN 翻译表，严禁 CASE WHEN / LIKE 伪造品类名
- `src/prompts.py` 规则 12：同上

---

#### Bug 5（自查发现）：我自己给出的"标准答案"环比跌幅 Top 10 有误

**现象**：我给出的环比跌幅 Top 10 遗漏了 `arts_and_craftmanship`、`security_and_services`、`music`、`fashion_childrens_clothes`（这 4 个品类真实跌幅均 ≥ -71%）。

**根因**：我的验证 SQL 先按**绝对跌幅** `LIMIT 15`，再从该子集按百分比重排。上述 4 个品类绝对金额小（-130、-100、-274、-100），未进 LIMIT 15，被错误排除。

**正确的环比跌幅 Top 10**（已修正，可作为后续对照基准）：

| 排名 | 品类 | Q3 | Q4 | 环比跌幅 |
|:---:|---|---:|---:|---:|
| 1 | small_appliances_home_oven_and_coffee | 750.05 | 0.00 | -100% |
| 2 | arts_and_craftmanship | 129.90 | 0.00 | -100% |
| 3 | security_and_services | 100.00 | 0.00 | -100% |
| 4 | fashio_female_clothing | 855.10 | 79.88 | -90.66% |
| 5 | music | 329.00 | 54.90 | -83.31% |
| 6 | fashion_sport | 720.30 | 179.70 | -75.05% |
| 7 | fashion_childrens_clothes | 139.89 | 39.99 | -71.41% |
| 8 | fixed_telephony | 17,255.18 | 5,694.63 | -67.00% |
| 9 | la_cuisine | 782.99 | 274.00 | -65.01% |
| 10 | dvds_blu_ray | 902.90 | 394.19 | -56.34% |

---

#### 修改文件汇总

| 文件 | 变更内容 |
|---|---|
| `src/tools.py` | `query_database()` 预览策略：≤100行全量，>100行截断+警告（原来只传3行） |
| `src/agent.py` | 规则6补充 canceled 过滤禁令；规则10新增 NULL 品类过滤要求；工作方式新增【数据完整性】 |
| `src/prompts.py` | 规则6补充 canceled 反例；规则13新增 NULL 品类过滤要求 |

---

## 当前停在

**Week 2 · Day 12-13 完成 + 数据一致性专项 QA 完成**

当前 Agent 具备的防护规则（`src/agent.py` SQL 规则 1-10）：
1. 只允许 SELECT
2. DuckDB 语法 + 双引号字段名
3. 优先 LEFT JOIN
4. 禁止多个一对多表直接 JOIN（Fan-out）
5. LEFT JOIN 后 COUNT 用字段而非 *
6. 禁止隐式过滤（含 canceled、状态过滤）
7. "X 中…"是分组维度，不是 WHERE
8. 增跌排名默认用百分比
9. 禁止自造品类标签（必须 JOIN 翻译表）
10. **[新增]** 必须过滤 NULL 品类（`product_category_name IS NOT NULL`）

手册进度：`AI数据分析Agent_完整开发手册_v2.md` 第 588 行（Day 12-13 结束）。
下次从 **Day 14：多轮记忆 + 上下文管理** 开始（手册第 589 行起）。

---

## 历史记录（2026-05-01）

### Week 2 · Day 12-13：多步分析能力

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 545–588 行**

#### 修改文件

**`src/agent.py`**

- **`AGENT_SYSTEM_PROMPT` 新增【多步分析规划】章节**，包含 4 条强制规则：
  1. 先输出纯文字分析计划（格式：`"分析计划：我将分 N 步完成这个分析：第1步…"`），不调工具
  2. 逐步调用工具，`intent` 参数与计划步骤描述一致
  3. 每步完成后用 1-2 句说明发现（下次 LLM 回复输出）
  4. 全部完成后综合结论
  以及 `make_chart` 前必须确认数据已查、对比图需两组数据都查完、必须显式传 `result_key`
- **`run_agent()` 加 `step_count` 步骤计数器**：在 `tool_calls_log` 每条记录里增加 `step` 字段（全局递增，跨 iteration 不重置）；status 显示从 `"🔧 调用工具: ..."` 升级为 `"第 N 步 🔧 \`tool_name\` — intent"`

**`src/app.py`**

- **`_render_message()` 折叠块标签加步骤号**：`f"第 {step_num} 步 🔧 {tool_name}: {intent_hint}"`，兼容旧消息（无 `step` 字段时用枚举序号 `i` 回退）
- **status 初始提示更新**：`"📖 读取问题，制定分析计划…"`（体现多步规划语义）

#### 交付标准对应

| 手册测试场景 | 预期 Agent 行为 |
|---|---|
| `"2017年总销售额"` | 1步：query_database → 直接给结论 |
| `"Top 10 销售品类"` | 2步：query_database（带 intent）→ make_chart（指定 result_key）→ 结论 |
| `"Q4 vs Q3 各品类对比"` | 多步：先输出分析计划 → query Q3 → query Q4 → analyze / make_chart → 综合结论 |

---

### Week 2 · Day 10-11：重构成 Agent 架构

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 336–542 行**

#### 新建文件

**`src/tools.py`**

- **`TOOLS_SCHEMA`**：3 个工具的 Function Calling JSON Schema 定义
- **`query_database(sql, intent, ds)`**：执行 SQL，结果存入 `session_state['query_results'][intent]`（带 df/sql/timestamp/row_count/columns），返回给 LLM 的是文字摘要（行数+列名+前3行），不传完整 DataFrame
- **`make_chart(chart_type, x_col, y_col, title, result_key, ds)`**：Plotly Express 绘图，Figure 存入 `session_state['_agent_charts']`，由 app.py 在 Agent 返回后统一渲染（确保历史消息图表可回放）
- **`analyze_dataframe(analysis_type, result_key)`**：describe / correlation / groupby_summary 三种统计分析，返回文字描述
- **`execute_tool(name, args, ds)`**：统一调度器，agent.py 只调这一个函数

**`src/agent.py`**

- **`AGENT_SYSTEM_PROMPT`**：Agent 专用 system prompt，包含工具说明 + 数据库结构占位符 + SQL 规则 + 工作方式，与 NL2SQL prompt 完全独立
- **`should_confirm(sql, estimated_rows) -> bool`**：智能确认（Week 2）：`estimated_rows > 100_000` 才返回 True；Week 1 是 `return True`
- **`run_agent(user_message, history, ds, status_container) -> dict`**：Agent 主循环
  - 组装 messages（system + 历史 + 当前问题）
  - 带 `tools=TOOLS_SCHEMA, tool_choice="auto", temperature=0.3` 调用 DeepSeek
  - 检测假 tool_calls（DeepSeek 偶发 None/空列表）
  - JSON 解析容错（json.JSONDecodeError → 返回错误消息给 LLM）
  - 智能确认检查（大查询暂停，返回 `needs_confirm` dict）
  - 实时进度：通过 `status_container.write()` 展示每步工具调用
  - 最大迭代次数 `MAX_ITERATIONS = 12`
  - 返回 `{final_answer, tool_calls_log, needs_confirm}`

#### 修改文件

**`src/app.py`**

- **移除旧 `call_llm()`**：替换为 `call_llm_for_fix()`，仅用于大查询确认执行报错时的 AI 修复，正常流程通过 `run_agent()` 处理
- **移除 `should_confirm()`**：逻辑迁移至 `agent.py`，Week 2 版本（`> 10万`）
- **`init_session_state()` 新增**：`query_results = {}`、`latest_query_key = None`、`_agent_charts = []`
- **`_render_message()` 增强**：渲染 `tool_calls_log`（每个工具调用展示为折叠 expander，含 SQL 预览和结果摘要）+ `charts`（Plotly 图表）；保留 Week 1 的 `sql` 字段兼容
- **`_render_pending()` 修订**：confirm 状态改为"大数据量确认"语义，确认后同时写入 `query_results`（供后续工具引用）；error 状态保持不变
- **新增 `_run_and_store_agent()`**：统一的 Agent 调用+结果存储函数，`render_chat` 和历史回放共用，避免代码重复
- **`render_chat()` 重构**：用户输入 → `st.status()` 实时展示进度 → `run_agent()` → 结果写入 messages → `st.rerun()`
- **Sidebar 新增"本轮已执行查询"区块**：展示 `query_results` 条目（倒序）、📋 查看 SQL、**↩️ 撤销上一步查询**按钮（删除最后一条 query_result + 最后一条 assistant 消息）
- **侧边栏历史回放改进**：▶ 按钮通过 `_replay_question` session_state key 触发 Agent 完整流程，而非直接进入 pending 状态

#### 架构决策说明

| 决策 | 原因 |
|---|---|
| `make_chart` 把 Figure 存入 `_agent_charts` 而非直接渲染 | Agent 在 `st.status()` 上下文内运行，直接调 `st.plotly_chart()` 会渲染在错误位置；统一由 app.py 渲染确保历史回放正常 |
| `should_confirm` 放在 `agent.py` 而非 `app.py` | 确认逻辑是 Agent 执行策略的一部分，与 LLM 调用紧耦合 |
| 大查询确认后不自动继续 Agent 循环 | 需要保存完整 messages 快照才能恢复，Week 2 简化处理；Week 3 可扩展 |
| `call_llm_for_fix` 保留独立 NL2SQL 修复路径 | 大查询确认后若执行失败，用简单 NL2SQL 修复比重启 Agent 循环更可预期 |

---

## 当前停在

**Week 2 · Day 10-11 完成**，已具备：
- 用户提问 → Agent 自动规划工具调用（NL2SQL + 画图 + 统计分析）
- 实时展示 Agent 思考进度（`st.status()` 面板）
- 小查询（< 10 万行）直接执行，大查询才弹确认框
- 侧边栏展示本轮已执行查询 + 撤销上一步
- 多轮对话历史传给 LLM（追问功能）

手册进度：`AI数据分析Agent_完整开发手册_v2.md` 第 542 行（Day 10-11 结束）。
下次从 **Day 12-14** 开始（手册第 543 行起）。

---

## 历史记录（2026-05-01 上午）

### Week 2 · Day 8-9：理解 DeepSeek Function Calling

无代码改动，学习阶段，掌握以下概念：
- Function Calling vs 普通 API 调用的区别（军师 vs 执行者模型）
- Agent 循环流程（messages → LLM → tool_calls → 执行 → 追加结果 → 继续）
- tools 参数 JSON Schema 写法
- tool_call_id 必须原值回传
- Parallel tool calls 处理方式
- DeepSeek 特有坑（假 tool_calls、JSON 非法、温度建议 0.3-0.5）

---

## 历史记录（2026-05-01 凌晨）

### Week 1 · Day 7：Schema 优化 + 确认机制预设计 [修订]

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 260–312 行**

#### 修改文件

**`src/data_source.py`**

- **新增 `OLIST_RELATIONSHIPS`**：9 条表关系 SQL 注释，描述各表的 JOIN 键和一对多关系（如 orders → order_items / order_payments / order_reviews）
- **新增 `get_schema_with_relationships()`**：在 schema 文本开头附加表关系说明，供 NL2SQL prompt 使用，帮助 LLM 在多表查询时选对 JOIN 键
- **新增 `estimate_row_count(sql)`**：将原 SQL 包裹在 `COUNT(*)` 子查询中预估返回行数，失败返回 -1

**`src/app.py`**

- **新增 `should_confirm(sql, estimated_rows) -> bool`**：封装"是否需要用户确认"判断逻辑；Week 1 阶段恒返回 True；Week 2 Day 10-11 已升级为智能判断（`> 10万` 才确认）
- **新增 `_parse_sql_meta(sql)`**：用正则提取涉及表名和是否含 JOIN，供确认卡片展示元信息
- **SQL 确认卡片改进**：在 SQL 预览前新增三列元信息卡片 —— 查询意图（中文）、涉及表名列表、是否含 JOIN、预估行数
- **新增侧边栏 SQL 历史**：`sql_history` 存入 `session_state`，最多保留 10 条（去重），每条附 ▶ 按钮可重新执行
- **`_render_message()` 增强**：message dict 新增 `question` 字段；历史渲染时在"查询完成"前用 `st.caption` 显示原始问题，方便历史回放时识别上下文

#### 超出手册的自主优化

**`src/app.py`**

- **新增 `_render_dataframe_with_total()`**：合计行拼接在主表末尾并高亮，单表渲染，下载时一并导出
- **新增 `_is_amount_col()` + `_AMOUNT_KEYWORDS`**：按列名关键词识别金额列（英/葡/中文），金额浮点列启用千位符 + 2 位小数，普通浮点列保留 2 位小数，金额整数列启用千位符

**`src/prompts.py`**

在 `NL2SQL_SYSTEM_PROMPT` 中新增 3 条硬性约束，解决多表查询数据不一致问题：

| 约束编号 | 内容摘要 | 解决的问题 |
|---|---|---|
| 9 | **优先使用 LEFT JOIN**，附属表必须用 LEFT JOIN，链式多表每个附属表单独评估 | INNER JOIN 静默丢行（如 SP 州 41,746 → 41,745）|
| 10 | **禁止多个一对多表直接 JOIN（Fan-out）**，必须先用 WITH/子查询分别聚合再 JOIN | 笛卡尔积膨胀导致 SUM/COUNT 虚高 |
| 11 | **NULL 与聚合函数一致性**：LEFT JOIN 后 `COUNT(*)` 改为 `COUNT(字段)`，必要时用 `COALESCE` 补零 | `COUNT(*)` 把无匹配行也计入统计 |

#### Bug 修复

| 问题 | 根因 | 解法 |
|---|---|---|
| `ValueError: Cannot specify ',' with 's'` | 合计行第一列为字符串 `"合计"`，concat 后列 dtype → object；列名含 `payment` 被识别为金额列，格式字符串 `{:,}` 作用于字符串值报错 | 改用 callable lambda formatter，`isinstance` 类型检查，非数值直接 `str(x)` 返回 |
| 历史回放时看不出查询的是什么问题 | message 存储时未保存 `question` 字段，渲染时无从展示 | message dict 新增 `question`；`_render_message()` 在内容前 `st.caption` 展示原始问题 |

---

## 历史记录（2026-04-30）

### Week 1 · Day 5-6：接通 DeepSeek 实现 NL2SQL

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 200–258 行**

#### 新建文件

**`src/config.py`**
- 从 `.env` 读取 `DEEPSEEK_API_KEY`
- 定义 LLM 相关常量：`DEEPSEEK_BASE_URL`、`MODEL_NAME`、`MAX_TOKENS`、`LARGE_QUERY_ROW_THRESHOLD`

**`src/prompts.py`**
- 定义 `NL2SQL_SYSTEM_PROMPT`：角色、任务、8 条硬性约束（含禁止隐式过滤）
- `build_nl2sql_prompt(user_question, schema_text)`：动态拼接 user prompt，末尾附"生成 SQL 前必读"强提醒
- `build_fix_prompt(...)`：SQL 执行报错时，将错误信息 + 原 SQL 发给 LLM 请求修复

#### 修改文件

**`src/app.py`**
- 新增 `call_llm(user_prompt)`：调用 DeepSeek API，`temperature=0` 保证确定性
- 新增 `pending` 状态机（存于 `session_state`），实现跨 rerun 的多步交互流程
- 新增 `_render_message()`：渲染历史消息，支持附带 SQL 折叠块和 DataFrame 结果表格
- 新增 `_render_pending()`：渲染待确认 / 待修复区块
- `render_chat()` 重构：历史渲染 → pending 区块 → 输入框，三段清晰分离

#### 问题修复

| 问题 | 根因 | 解法 |
|---|---|---|
| `No module named 'openai'` | `.venv` 环境缺依赖 | `pip install openai python-dotenv` |
| LLM 丢失 installments=0/1 的行 | 把"分期付款中"解读为 `WHERE > 1` | system prompt 加第 6-8 条禁止隐式过滤；`temperature` 降为 0 |
