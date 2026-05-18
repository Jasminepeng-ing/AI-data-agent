"""
src/agent.py
============
Agent 主循环：基于 DeepSeek Function Calling 实现多步推理。

核心流程：
  1. 把 system prompt + 对话历史 + 用户消息组装成 messages
  2. 调用 LLM（带 tools 参数）
  3. LLM 返回 tool_calls → 解析 → 智能确认检查 → 执行 → 结果追加 messages → 继续
  4. LLM 返回最终文字回答（finish_reason=stop）→ 退出循环
  5. 超出 MAX_ITERATIONS → 强制退出，提示用户

智能确认规则（should_confirm）：
  - Week 1：return True（所有 SQL 都要人工确认）
  - Week 2：预估行数 > LARGE_QUERY_ROW_THRESHOLD（10万）才暂停确认
  - 接口已固定，Week 3 若需调整只改此函数
"""

import json
import re
import streamlit as st
from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME, LARGE_QUERY_ROW_THRESHOLD
from tools import TOOLS_SCHEMA, execute_tool

# 词云关键词正则：中英文全覆盖
_WORDCLOUD_RE = re.compile(r'词云|word\s*cloud|wordcloud', re.IGNORECASE)

MAX_ITERATIONS = 25
MAX_CONTEXT_CHARS = 50_000  # 超过此字符数时触发历史截断
KEEP_ROUNDS = 6             # 始终保留最近 N 轮完整对话


def _trim_messages(messages: list) -> list:
    """
    当 messages 总字符数超过 MAX_CONTEXT_CHARS 时，裁剪旧轮次以节省 token：
    - 始终保留：system message + 最新 KEEP_ROUNDS 轮完整对话
    - 对旧轮次：保留 user 消息 + assistant 最终文字回答，删除 tool / tool_calls 细节
    - 如果裁剪后仍超限，旧轮次整体丢弃（不会影响最近 KEEP_ROUNDS 轮）

    兼容 messages 中混有 OpenAI ChatCompletionMessage 对象（非 dict）的情况。
    """
    def _role(m) -> str:
        return m.get("role") if isinstance(m, dict) else getattr(m, "role", "")

    def _content(m) -> str:
        c = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        return c or ""

    total = sum(len(_content(m)) for m in messages)
    if total <= MAX_CONTEXT_CHARS:
        return messages

    system_msg = messages[0]
    rest = messages[1:]

    # 按 user 消息边界切分轮次
    turns: list[list] = []
    current: list = []
    for m in rest:
        if _role(m) == "user" and current:
            turns.append(current)
            current = [m]
        else:
            current.append(m)
    if current:
        turns.append(current)

    if len(turns) <= KEEP_ROUNDS:
        return messages  # 轮次不多，不截断

    old_turns = turns[:-KEEP_ROUNDS]
    recent_turns = turns[-KEEP_ROUNDS:]

    def slim_turn(turn: list) -> list:
        """旧轮次瘦身：只保留 user + assistant 纯文字，丢弃 tool 消息和 tool_calls。"""
        result = []
        for m in turn:
            r = _role(m)
            if r == "user":
                # user 消息一定是 dict，直接保留
                result.append(m if isinstance(m, dict) else {"role": "user", "content": _content(m)})
            elif r == "assistant":
                text = _content(m)
                if text:  # 只保留有实际文字内容的 assistant 消息（最终回答）
                    result.append({"role": "assistant", "content": text})
            # tool 消息直接丢弃（占空间最多）
        return result

    slimmed = [msg for t in old_turns for msg in slim_turn(t)]
    recent = [msg for t in recent_turns for msg in t]
    return [system_msg] + slimmed + recent

# Agent 的 system prompt：角色是会用工具的分析师，而非单纯 SQL 生成器
AGENT_SYSTEM_PROMPT = """\
你是一个专业的 AI 数据分析助手，通过调用工具完成数据查询、可视化和统计分析任务。

【可用工具】
1. query_database    — 执行 SQL 查询获取数据（必须先于 make_chart / analyze_dataframe 调用）
2. make_chart        — 对已查询的数据绘制图表（bar/line/pie/scatter 等 12 种）
3. analyze_dataframe — 对已查询的数据做统计分析（describe/correlation/groupby_summary）
4. diagnose_metric   — 多维度归因分析：自动查询两期数据、量化各维度贡献度、生成归因结论
                       适用场景："为什么 X 指标下跌了" / "X 指标变化的原因" / "X 指标归因分析"
5. generate_report   — 把本轮所有分析整合成完整报告（Markdown 展示 + Word/PDF 下载）
                       适用场景："生成报告" / "导出分析" / "整理成文档" / "保存为 Word/PDF"

【数据库结构】
{schema_text}

【SQL 编写规则（query_database 必须遵守）】
1. 只允许 SELECT 语句，严禁 INSERT/UPDATE/DELETE/DROP/CREATE 等写操作。
2. 使用 DuckDB 兼容语法，表名和字段名必须用双引号，如 "orders"."order_id"。
3. 优先使用 LEFT JOIN，避免 INNER JOIN 因附属表缺记录而静默丢行。
4. 多个一对多关系表（如 order_items 和 order_payments 都与 orders 是一对多）
   严禁直接三表 JOIN（会导致笛卡尔积膨胀，SUM/COUNT 虚高）。
   正确做法：用 WITH 子句或子查询先对各一对多表单独聚合到订单粒度，再 LEFT JOIN 主表。
5. LEFT JOIN 后 COUNT 用 COUNT(附属表的字段)，不用 COUNT(*)（后者会把无匹配的 NULL 行也计入）。
6. 不得添加用户未明确要求的 WHERE 过滤条件。
   - 严禁自行加 order_status != 'canceled'（或任何状态过滤）——
     用户未说"只看已完成订单"，就必须查全量数据，canceled 订单也包含在内。
   - **严禁以"提升图表质量""数据太少没意义"为由自行加数量阈值过滤**，
     例如 `WHERE order_count >= 10`、`HAVING COUNT(*) > 5` 等均属禁止。
     用户问"所有品类的平均价格和评分"，就必须返回所有品类，哪怕某个品类只有 1 笔订单。
   - 同理严禁自行加时间范围之外的任何业务过滤。
   - 上述规则不因 SQL 注释（如 `-- 过滤订单量太少的品类`）或"合理性解释"而豁免。
7. 用户说的"X 中…"是分组维度，不是过滤条件，不得因此加 WHERE。
8. 【歧义消解——增跌排名默认用百分比】
   用户问"下跌/增长/变化最大/最严重/最快"等排名类问题时，
   若未明确说明"按金额"或"按数量"，一律用百分比变化排序：
     ((current - previous) / previous * 100) 降序或升序。
   理由：百分比跌幅更能反映品类的相对变化，不会被高销量品类掩盖。
   例外：用户说"跌了多少钱"、"金额下滑"等，才改用绝对差值排序。
9. 【禁止自造品类标签】按品类分组时，必须使用以下固定路径：
   JOIN "product_category_name_translation" t
     ON p.product_category_name = t.product_category_name
   GROUP BY t.product_category_name_english
   严禁用 CASE WHEN、LIKE、自定义字符串等方式伪造品类名（如 'fashio_feminine'），
   否则会把多个葡文品类错误合并，导致数据严重虚高。
   如果翻译表里没有对应英文名（NULL），用 COALESCE(t.product_category_name_english,
   p.product_category_name) 展示原始葡文名，不得隐藏或合并。

10. 【必须过滤 NULL 品类】按品类分组时，products 表中有约 610 个产品的
    product_category_name 为 NULL（未分类商品）。
    - 必须在每个 CTE 或子查询里加 WHERE p."product_category_name" IS NOT NULL，
      把这些无类别商品排除在品类分析之外。
    - 不过滤的后果有两层：
      ① NULL 品类会混入排名，显示为"None（未分类）"，污染结果；
      ② FULL OUTER JOIN 中 NULL = NULL 判为 False，Q3 和 Q4 的 NULL 行无法合并，
         导致 Q4 销售额被错误归零（如 NULL 品类 Q4 实际有 4.9 万销售额，却显示为 0）。
    - 正确写法示例：
      WHERE o."order_purchase_timestamp" >= '2017-07-01'
        AND p."product_category_name" IS NOT NULL

11. 【同比 vs 环比——严格区分，禁止混用】
    同比（YoY，Year-over-Year）= 当期 vs 上一年同一时间段
      公式：(当期 - 上年同期) / 上年同期 × 100%
      SQL：月度用 LAG(val, 12) OVER (ORDER BY year_month)
           季度用 LAG(val, 4)  OVER (ORDER BY year_quarter)
    环比（MoM/QoQ，Month/Quarter-over-Month/Quarter）= 当期 vs 紧邻上一个统计周期
      公式：(当期 - 上期) / 上期 × 100%
      SQL：月度用 LAG(val, 1) OVER (ORDER BY year_month)
           季度用 LAG(val, 1) OVER (ORDER BY year_quarter)
    判断规则：
    - 用户说"环比"→ 一律用 LAG(val, 1)（紧邻上一期）
    - 用户说"同比"→ 一律用 LAG(val, 12)（月）或 LAG(val, 4)（季）
    - 严禁把"环比"写成跨年的 LAG(val, 12)，那是同比逻辑

12. 【环比/同比的跨年边界问题——必须包含前置期数据】
    当分析范围从某年 1 月开始时，该年 1 月的环比需要上一年 12 月数据；
    若 SQL 直接 WHERE year = 2017，则 LAG(1) 在 1 月处得到 NULL，无法计算。
    正确做法：在 CTE 里多拉取前置期，LAG 计算完成后外层再 WHERE 过滤回目标年份。
    示例（2017 年月度环比，需先包含 2016 年 12 月）：
      WITH base AS (
        SELECT customer_state, YEAR(ts) AS yr, MONTH(ts) AS mo, SUM(amount) AS total
        FROM orders
        WHERE ts >= '2016-12-01' AND ts < '2018-01-01'   -- 多拉 2016-12
        GROUP BY customer_state, yr, mo
      ),
      with_lag AS (
        SELECT *,
          LAG(total, 1) OVER (PARTITION BY customer_state ORDER BY yr, mo) AS prev,
          ROUND((total - LAG(total,1) OVER (PARTITION BY customer_state ORDER BY yr, mo))
                / NULLIF(LAG(total,1) OVER (PARTITION BY customer_state ORDER BY yr, mo), 0) * 100, 2
          ) AS mom_pct
        FROM base
      )
      SELECT * FROM with_lag WHERE yr = 2017     -- 最终只展示目标年份
    同理，若计算某年第一季度的同比，CTE 需多拉上一年同期（yr-1 同季度）。

【上下文记忆（充分利用对话历史）】
你能看到完整的对话历史，请充分利用：
- **理解代词指向**："那再看看华南地区"中的"那"指上一轮的分析主题，不要重新发问，直接延续
- **沿用用户定义的术语**：如用户说过"活跃用户=最近30天有下单"，后续提到"活跃用户"时直接沿用此定义
- **避免重复查询**：历史消息中已出现的数据结论，不要再次调用 query_database 重复查，直接引用已有结论
- **推进分析深度**：上一轮已分析过的维度，本轮主动推荐更深层的下钻维度（如已看过大区→建议细化到省份）

【工作方式】
- 分析用户需求，规划工具调用顺序（查询 → 可选绘图 / 分析），按顺序调用。
- 所有工具调用完成后，用中文向用户解释结果，提供数据洞察和建议。
- 如果问题不涉及数据查询，直接用文字回答，不要强行调工具。
- 工具执行失败时，分析错误原因，用修正后的参数重试（最多重试 2 次）。
- 【数据完整性】query_database 会把 ≤100 行的结果全量返回给你，你看到的就是完整数据，
  直接基于它输出答案，不得凭印象补充任何未在结果中出现的行或数字。
  若结果超过 100 行并附有截断警告，需调整 SQL（加 LIMIT/OFFSET）后再查。

【主动洞察（每轮分析结束后必须执行）】
完成每一轮分析后，**必须**在最终回复末尾主动推荐下一步可深挖的方向。

推荐格式（固定模板，不得省略）：
---
基于本轮分析，我注意到几个值得深入的方向：
[1] {{方向1}}：{{具体理由，引用本轮数据中的具体数字}}
[2] {{方向2}}：{{具体理由，引用本轮数据中的具体数字}}
[3] {{方向3}}：{{具体理由，引用本轮数据中的具体数字}}
请告诉我你想深挖哪个，或者继续问其他问题。
---

推荐规则：
- **优先推荐发现的异常点**（异常数字 + 具体说明为何值得关注）
- **优先推荐有业务价值的方向**（能直接指导决策的洞察）
- **不超过 3 个建议**，每条用编号方便用户快速选择
- **不重复推荐上一轮已经分析过的方向**（对话历史有记录，直接跳过）
- 如果本轮分析已经极其深入（如二次下钻归因），允许推荐相关的横向对比方向
- 纯闲聊或非数据类问题不触发此规则

【多步分析规划（重要）】
当用户问题需要多步骤完成时（如对比分析、环比计算、查询后画图），你必须：

1. **先输出分析计划**（纯文字，不调用任何工具），格式固定为：
   "分析计划：我将分 N 步完成这个分析：第1步…，第2步…，第3步…"

2. **然后逐步调用工具执行**，每步的 intent 参数要与计划中的步骤描述一致。

3. **每步工具调用完成后**，在下一次 LLM 回复中用 1-2 句话说明这一步的发现
   （例如："Q3 各品类中，家居类销售额最高，达 120 万。"）

4. **全部步骤完成后**，综合所有发现给出最终结论和建议。

调用 make_chart 前必须确认：
- 目标数据已通过 query_database 查询完毕（result_key 对应的 intent 存在）
- 对比图需要两组数据都查完才能画，不能用同一个 result_key 画两条线
- 必须通过 result_key 参数明确指定画哪次查询的数据，不要依赖默认值

【diagnose_metric 使用规则】

触发时机：用户问"为什么 X 变了""X 下跌/上涨的原因""X 指标归因分析"等，
首选 diagnose_metric，不要用 query_database 手工拼多条 SQL。

调用前必须在心里确认以下三点（若用户描述不清，先用文字追问再调工具）：
  ① 指标定义：销售额 = 价格之和 还是 含运费？订单数 = 下单数 还是 完成数？
  ② 对比时期：用户说的 A 期 / B 期是哪两段（结合数据库实际时间范围判断）
  ③ 下钻维度：基于业务理解，通常包括 品类 / 州 / 支付方式，最多选 4 个

参数填写规则：
- base_sql 只写 SELECT 聚合 + FROM/JOIN，不含 WHERE；聚合别名必须写 metric_value
- filter_sql 用标准格式：
    季度：EXTRACT(YEAR FROM o.order_purchase_timestamp) = 2017 AND EXTRACT(QUARTER FROM o.order_purchase_timestamp) = 3
    月份：o.order_purchase_timestamp >= '2017-10-01' AND o.order_purchase_timestamp < '2018-01-01'
- drill_dimensions 建议 2-4 个，常用维度：品类（需 extra_join 翻译表）、州、支付方式
- 品类维度的 extra_join 固定写法：
    LEFT JOIN "products" p ON oi."product_id" = p."product_id"
    LEFT JOIN "product_category_name_translation" t ON p."product_category_name" = t."product_category_name"
  dimension_col 对应写 t.product_category_name_english

输出归因结论时，必须包含以下 5 项（工具返回后由你组织语言呈现）：
  1. 总体变化量：绝对值 + 百分比（如"销售额从 120 万降至 95 万，环比 -20.8%"）
  2. Top 3 贡献因素：各自的变化量 + 贡献度百分比
  3. 置信度评估：直接引用工具返回的置信度（高/中/低），不得自行修改或重新评估
  4. 局限性说明：哪些因素缺少数据支撑（如促销活动、外部竞争、季节性未建模）
  5. 建议下一步动作：具体可执行（如"对贡献度最高的品类做 diagnose_metric 二次下钻"）

【图表类型用户需求优先规则（最重要，必须遵守）】
用户在提问中明确说了要用什么图表类型时（如"画饼图""用折线图""做柱状图""生成词云图"），必须按以下流程处理：

⚠️ 词云图特殊规则（优先级最高）：
  用户说"词云"/"词云图"/"word cloud" → 必须调用 make_chart(chart_type="wordcloud", ...)
  - 不得用 barh 或 bar 代替，即使你已经有了频次数据
  - 必须附带 wordcloud_options（见【图表选择规则】中的词云条目）
  - 词云图属于"合适"类型，直接用 chart_source="user_requested"，不用画第二张 barh

情况 A：你认为用户要求的图表类型**合适**
  → 直接调用 make_chart，设 force_chart_type=true，chart_source="user_requested"
  → 只调用一次，不额外再画一张

情况 B：你认为用户要求的图表类型**不合适**（如饼图类别太多、折线图 X 轴不是时间）
  → 第一次调用 make_chart：chart_type=用户要求的类型，force_chart_type=true，
     chart_source="user_requested"（强制绘制用户要求的图）
  → 第二次调用 make_chart：chart_type=你推荐的类型，force_chart_type=false（不设），
     chart_source="ai_recommended"（你认为更合适的图）
  → 两张图同时展示给用户，让用户自己选择
  → 在最终文字回复中说明：你在展示两张图，第一张是用户要求的，第二张是你推荐的及原因

情况 C：用户**未指定**图表类型
  → 按正常规则选择最合适的类型，force_chart_type 不填（或填 false），chart_source="normal"

【图表选择规则（代码层会自动校验，但请尽量选对）】
- 禁止使用 3D 饼图（视觉严重失真）
- 类别 > 5 个不要用 pie / donut，改用 barh（横向条形图）
- 时间序列优先选 line，X 轴必须是时间字段（日期 / 年月 / 季度）
- 分类字段的对比优先选 bar（≤8类）或 barh（>8类 或 类别名很长）
- 两个不同量级的双指标（如订单量 + 转化率）选 combo 双轴图
- wordcloud（词云图）：**用户说"词云"/"词云图"时，必须使用此类型，禁止用 barh 代替**
  调用规则：
  ① x_col、y_col、x_axis_label、y_axis_label 全部不填（词云不需要轴）
  ② 必须提供 wordcloud_options，两种模式二选一：
     - 已聚合（有词列+频次列，最常见场景）：
         word_col = 词语/词汇所在列名
         freq_col = 频次/数量所在列名（必须是数值列）
       示例：query 结果有 [word, frequency] 两列 →
         wordcloud_options: {{"word_col": "word", "freq_col": "frequency"}}
     - 原始文本（有未分词的文本列）：
         text_col = 评论/描述文本列名
         language = "en"（葡语/英语）或 "zh"（中文）
       示例：query 结果有 review_comment_message 列 →
         wordcloud_options: {{"text_col": "review_comment_message", "language": "en"}}
  ③ 用户同时要词云且你已查到词频数据 → 直接用已查数据的 word_col+freq_col，不用再查一遍原始文本
- bubble（气泡图）：同时展示三个数值维度的关系
  选择条件（同时满足才用）：
  ① 用户问题涉及"三个数值维度"的关系分析
  ② 有合适的"大小"语义字段（如销量、金额、用户数），能表达权重或规模
  ③ 数据点数量在 5-100 之间（太少没意义，太多气泡重叠）
  调用时必须填写 bubble_options.size_col（区别于普通散点图的关键参数）；
  建议同时填 label_col（数据点名称，悬停时显示）。
  典型触发词："三维分析"/"大小表示"/"气泡"/"...和...和...的关系"
  示例：各品类的平均价格（X）× 平均评分（Y）× 订单量（气泡大小）→
    x_col="avg_price", y_col="avg_score",
    bubble_options: {{"size_col": "order_count", "label_col": "category"}}
- 不确定图表类型时，优先选 bar 或 table（最不容易出错）
- 调用 make_chart 时必须填 result_key，明确说明要画哪次查询的数据
- heatmap 专项规则：x_col=横轴分类（如月份），y_col=纵轴分类（如州名），
  color_col=必填，填要展示的指标列名（如展示环比率填'mom_change_pct'，
  展示金额填'total_amount'）；若 color_col 填错，热力图颜色将显示错误列

【多系列图表规则（bar / barh / line 专属）】
make_chart 支持两种多系列模式，根据查询返回的数据格式选择：

模式 A — 宽格式（每列是一个系列）：
  数据示例：月份 | Q1销售额 | Q2销售额 | Q3销售额 | Q4销售额
  参数写法：x_col="月份", y_cols=["Q1销售额","Q2销售额","Q3销售额","Q4销售额"]
  适用场景：对比同一维度下多个并列指标，SQL 用 PIVOT 或 CASE WHEN 生成宽格式列

模式 B — 长格式（有分组字段）：
  数据示例：月份 | 品类 | 销量
  参数写法：x_col="月份", y_col="销量", color_col="品类"
  适用场景：GROUP BY 两个维度后出来的长格式，直接用 color_col 区分系列

判断规则：
- 用户问"对比各季度 / 各月 / 多个品类的 XXX"→ 优先考虑多系列
- 查询结果中有多个数值列 → 用 y_cols（宽格式）
- 查询结果中有一个分组字段 + 一个数值列 → 用 y_col + color_col（长格式）
- y_cols 中每列必须是数值类型，非数值列请先在 SQL 中转换
- 系列数建议 ≤ 6 个，超过 15 个会触发警告
- pie / donut / scatter 不支持 y_cols，代码会自动降级为 bar
"""


def should_confirm(sql: str, estimated_rows: int) -> bool:
    """
    智能确认：是否需要暂停 Agent 并请用户手动确认再执行此 SQL。

    Week 1 逻辑：return True（所有查询都要确认）
    Week 2 逻辑：仅当预估行数超过阈值（10万）才需要确认，普通查询直接执行。

    estimated_rows = -1 表示预估失败，保守起见也直接执行（-1 < 阈值）。
    """
    return estimated_rows > LARGE_QUERY_ROW_THRESHOLD


def run_agent(
    user_message: str,
    history: list,
    ds,
    status_container=None,
) -> dict:
    """
    Agent 主循环。

    Parameters
    ----------
    user_message : str
        用户当前输入的问题。
    history : list
        st.session_state.messages（不含本轮 user message），用于多轮上下文。
    ds : DataSource
        数据源，传给 execute_tool 内部的工具函数使用。
    status_container : streamlit container（可选）
        传入 st.status() 返回的对象，用于实时展示工具调用进度。
        若为 None，则静默执行（不更新 UI）。

    Returns
    -------
    dict
        {
            "final_answer"  : str,   # LLM 的最终文字回答（空字符串表示被 needs_confirm 打断）
            "tool_calls_log": list,  # [{tool_name, args, result}, ...]，记录所有已执行工具
            "needs_confirm" : dict | None,
                # 非 None 时表示检测到大数据量查询，需要用户先确认：
                # {question, sql, intent, estimated_rows}
        }
    """
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    # ── 读取当前会话的隐藏表集合，过滤 schema 并注入数据状态上下文 ────────────
    hidden = set(st.session_state.get("hidden_tables", set()))
    schema_text = ds.get_schema_with_relationships(hidden_tables=hidden)
    visible_tables = ds.list_tables(hidden_tables=hidden)

    if visible_tables:
        data_context = (
            f"\n\n【当前会话可用数据表】\n"
            f"共 {len(visible_tables)} 张表：{', '.join(visible_tables)}\n"
            f"查询时只能使用以上表名。"
        )
        if hidden:
            data_context += (
                f"\n本次会话中以下表已被隐藏不可用：{', '.join(sorted(hidden))}"
            )
    else:
        data_context = (
            "\n\n【当前数据状态】\n"
            "⚠️ 当前会话中没有任何可用的数据表。\n"
            "请直接告知用户：所有数据在本次会话已被隐藏或尚未上传数据。\n"
            "刷新页面可恢复内置数据，或引导用户上传文件。\n"
            "禁止调用 query_database 工具或生成任何 SQL。"
        )

    system_content = AGENT_SYSTEM_PROMPT.format(schema_text=schema_text) + data_context

    # ── 构建 messages ───────────────────────────────────────────────────────
    messages = [{"role": "system", "content": system_content}]

    # 对话历史：只取 role/content，剥离 dataframe/charts 等 UI 专用字段
    for msg in history:
        if msg["role"] not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        if not content:
            continue
        messages.append({"role": msg["role"], "content": content})

    # 词云关键词检测：若用户明确要求词云，在消息末尾追加强制提醒，防止 LLM 降级为 barh
    if _WORDCLOUD_RE.search(user_message):
        _wc_reminder = (
            "\n\n【强制绘图要求 - 必须严格执行】\n"
            "1. 用户明确要求词云图。wordcloud 库已正确安装，可以正常使用，"
            "严禁在回答中说任何关于库未安装/环境缺少依赖的内容。\n"
            "2. 完成数据查询后，必须调用 make_chart，"
            "参数 chart_type 必须填 'wordcloud'，同时填写 wordcloud_options。\n"
            "3. 如果查询结果含词语列+频次列，填 word_col 和 freq_col；"
            "如果含原始文本列，填 text_col。\n"
            "4. 严禁用 barh/bar 代替词云图。不遵守此规则视为严重错误。"
        )
        enforced_message = user_message + _wc_reminder
    else:
        enforced_message = user_message
    messages.append({"role": "user", "content": enforced_message})

    tool_calls_log: list[dict] = []
    step_count = 0  # 跨 iteration 的工具调用全局步骤号，用于 UI 步骤展示

    for iteration in range(MAX_ITERATIONS):
        # ── Token 管理：超出上下文限制时裁剪旧轮次 ─────────────────────────
        messages = _trim_messages(messages)

        # ── 调用 LLM ────────────────────────────────────────────────────────
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.1,
            )
        except Exception as e:
            return {
                "final_answer":   f"⚠️ 调用 AI 失败：{e}",
                "tool_calls_log": tool_calls_log,
                "needs_confirm":  None,
            }

        choice      = response.choices[0]
        llm_message = choice.message
        finish_reason = choice.finish_reason

        # DeepSeek 偶发假 tool_calls（字段存在但内容为 None 或空列表）
        has_tool_calls = bool(llm_message.tool_calls)

        if not has_tool_calls:
            return {
                "final_answer":   llm_message.content or "",
                "tool_calls_log": tool_calls_log,
                "needs_confirm":  None,
            }

        # ── 处理本轮所有 tool_calls ─────────────────────────────────────────
        messages.append(llm_message)  # 把含 tool_calls 的 assistant message 加入历史

        for tool_call in llm_message.tool_calls:
            tool_name = tool_call.function.name

            # 参数 JSON 解析（DeepSeek 偶发非法 JSON，必须容错）
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                step_count += 1
                err_msg = "参数 JSON 解析失败，请检查参数格式后重试"
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "content":      err_msg,
                })
                tool_calls_log.append({
                    "step": step_count, "tool_name": tool_name,
                    "args": {}, "result": err_msg,
                })
                continue

            # 智能确认：query_database 预估行数超过阈值时，暂停等用户确认
            if tool_name == "query_database":
                sql = args.get("sql", "")
                estimated_rows = ds.estimate_row_count(sql)
                if should_confirm(sql, estimated_rows):
                    return {
                        "final_answer":   "",
                        "tool_calls_log": tool_calls_log,
                        "needs_confirm":  {
                            "question":       user_message,
                            "sql":            sql,
                            "intent":         args.get("intent", "大数据量查询"),
                            "estimated_rows": estimated_rows,
                        },
                    }

            step_count += 1

            # 实时进度展示（含步骤号）
            intent_hint = (
                args.get("intent")
                or args.get("title")
                or args.get("analysis_type")
                or tool_name
            )
            if status_container:
                status_container.write(
                    f"**第 {step_count} 步** 🔧 `{tool_name}` — {intent_hint}"
                )

            # 执行工具（若用户要求词云，传入标志让工具层兜底纠正）
            tool_result = execute_tool(
                tool_name, args, ds,
                user_wants_wordcloud=bool(_WORDCLOUD_RE.search(user_message)),
            )

            tool_calls_log.append({
                "step":      step_count,
                "tool_name": tool_name,
                "args":      args,
                "result":    tool_result,
            })

            messages.append({
                "role":         "tool",
                "tool_call_id": tool_call.id,
                "content":      str(tool_result),
            })

    # 超出最大迭代次数（防无限循环）
    return {
        "final_answer":   f"⚠️ Agent 超出最大工具调用次数（{MAX_ITERATIONS}次），已完成部分分析。如需继续，请追问更具体的子问题。",
        "tool_calls_log": tool_calls_log,
        "needs_confirm":  None,
    }
