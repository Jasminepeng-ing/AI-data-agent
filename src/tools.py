"""
src/tools.py
============
Agent 工具集：工具函数实现、Function Calling JSON Schema、工具调度器。

工具列表（Week 3 Day 18-20）：
  1. query_database    — 执行 SQL，结果缓存到 session_state['query_results'][intent]
  2. make_chart        — 支持 10 种图表类型，含自动校验降级 + insight + 原始数据 expander
  3. analyze_dataframe — 对缓存数据做描述统计 / 相关性 / 分组概览
  4. diagnose_metric   — 多维度归因分析：自动拼接 SQL、计算贡献度、LLM 生成结论

设计原则：
  - 工具函数只写 session_state，不直接调用 st.write()，UI 渲染交给 app.py
  - make_chart 把 {fig, warning, insight, df} 整体存入 _agent_charts，供 app.py 渲染
  - diagnose_metric 把结构化结果存入 _diagnose_results，供 app.py 后续渲染
  - execute_tool() 是统一调度入口，agent.py 只调这一个函数
"""

import re
from datetime import datetime

import pandas as pd
import streamlit as st
from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME
import chart_utils
from validators import validate_chart_type, validate_diagnose_params, validate_wordcloud_input

# 统一色板（Seaborn "deep" 系列，适合商业报表）
COLOR_PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
    "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
]

# 轴刻度格式：< 1k 直接显示，1k-1M 用 k，1M-1B 用 M，≥ 1B 用 G（SI 标准，即十亿）
_TICK_FMT_STOPS = [
    dict(dtickrange=[None, 1000], value=".2~f"),    # 步长 < 1k → 保留最多2位小数
    dict(dtickrange=[1000, 1e6],  value=".3~s"),    # 步长 1k-1M → 41.7k / 200k
    dict(dtickrange=[1e6, 1e9],   value=".3~s"),    # 步长 1M-1B → 3.20M
    dict(dtickrange=[1e9, None],  value=".3~s"),    # 步长 ≥ 1B  → 1.23G
]


def _apply_tick_format(fig, axes: tuple = ("y",)) -> None:
    """对指定轴批量应用 k/M/G 数字格式，axes 可含 'x' / 'y' / 'y2'。"""
    if "y" in axes:
        fig.update_yaxes(tickformatstops=_TICK_FMT_STOPS, secondary_y=False)
    if "y2" in axes:
        fig.update_yaxes(tickformatstops=_TICK_FMT_STOPS, secondary_y=True)
    if "x" in axes:
        fig.update_xaxes(tickformatstops=_TICK_FMT_STOPS)


# ── Function Calling JSON Schema ──────────────────────────────────────────────
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": (
                "执行 SQL 查询，返回结果概要。"
                "结果会存入带意图标签的缓存，供 make_chart 和 analyze_dataframe 使用。"
                "凡是需要查数据库的需求，都必须先调用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": (
                            "要执行的 SELECT SQL 语句（只能是 SELECT，DuckDB 方言）。"
                            "表名和字段名必须用双引号括起来，如 \"orders\".\"order_id\"。"
                        ),
                    },
                    "intent": {
                        "type": "string",
                        "description": (
                            "用一句中文说明这个查询的意图，如'查2017年各品类销售额'。"
                            "此标签作为结果缓存的 key，make_chart/analyze_dataframe "
                            "可通过 result_key 参数指定使用哪次查询的数据。"
                        ),
                    },
                },
                "required": ["sql", "intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_chart",
            "description": (
                "根据查询结果生成交互式图表。\n"
                "【图表类型优先级规则】\n"
                "1. 若用户在提问中明确指定了图表类型，必须用 force_chart_type=true 强制使用该类型；\n"
                "2. 若你认为用户指定的类型不合适（如 pie 画 20 个类别），"
                "则再额外调用一次 make_chart（不设 force_chart_type）生成你推荐的类型，"
                "两张图都返回给用户选择；\n"
                "3. 若用户未指定图表类型，按正常规则选择最合适的类型即可。\n"
                "必须先调用 query_database 才能使用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "enum": [
                            "line", "bar", "barh", "pie", "donut",
                            "scatter", "heatmap", "area", "combo", "table",
                            "wordcloud", "bubble",
                        ],
                        "description": (
                            "图表类型。选择规则：\n"
                            "- line: 时间序列趋势（X轴必须是时间）\n"
                            "- bar: 分类对比（类别≤8个）\n"
                            "- barh: 横向条形图（类别名长 或 >8个）\n"
                            "- pie/donut: 构成占比（类别≤5个，总和有意义）\n"
                            "- scatter: 两个连续变量相关性（X和Y都必须是数值）\n"
                            "- heatmap: 二维交叉分析\n"
                            "- area: 累积量或占比变化\n"
                            "- combo: 双轴图（柱+线，不同单位的双指标）\n"
                            "- table: 精确数值查阅\n"
                            "- wordcloud: 词云图（文本词频可视化；"
                            "必须同时填写 wordcloud_options，x_col/y_col 可不填）\n"
                            "- bubble: 气泡图（三维数值分析；x_col/y_col 为两轴数值，"
                            "必须同时填写 bubble_options.size_col 指定气泡大小字段）\n"
                            "注意：代码层会对不合适的类型自动降级，但请尽量选对。"
                        ),
                    },
                    "x_col": {
                        "type": "string",
                        "description": (
                            "X 轴字段名（必须是查询结果的列名）。"
                            "词云图（wordcloud）不需要填写此参数。"
                            "barh 图例外：x_col 必须填度量值列（如订单量、金额等数值），"
                            "分类列（如州名、品类）填入 y_col。"
                        ),
                    },
                    "y_col": {
                        "type": "string",
                        "description": (
                            "Y 轴字段名（单系列时使用）。"
                            "多系列时改用 y_cols，y_col 与 y_cols 必须提供其中一个。"
                            "barh 图例外：y_col 必须填分类列（如州名、品类等字符串），"
                            "度量值列（如订单量、金额等数值）填入 x_col。"
                        ),
                    },
                    "y_cols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "多系列 Y 轴字段列表（宽格式数据，bar/barh/line 专用）。\n"
                            "当需要在同一图表中对比多个数值列时使用，"
                            "如 ['Q1销售额','Q2销售额','Q3销售额'] 或 ['苹果','香蕉','橙子']。\n"
                            "与 y_col 二选一：单系列用 y_col，多系列用 y_cols。\n"
                            "注意：y_cols 中每个字段都必须是数值类型；"
                            "长格式数据（有分组字段）请用 y_col + color_col 组合代替。"
                        ),
                    },
                    "y_col_2": {
                        "type": "string",
                        "description": "复合图（combo）的第二个Y轴字段（次指标），其他类型不填",
                    },
                    "color_col": {
                        "type": "string",
                        "description": (
                            "着色字段。"
                            "bar/line/area：多系列分组的分类列（可选）。"
                            "heatmap：必填，指定用哪列数值决定格子颜色"
                            "（如想展示环比率，填'mom_change_pct'而非'total_amount'）。"
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "图表标题（中文，建议包含时间维度，如'2017年各品类月度销售额'）",
                    },
                    "x_axis_label": {
                        "type": "string",
                        "description": "X 轴标题（带单位，如'月份'）",
                    },
                    "y_axis_label": {
                        "type": "string",
                        "description": (
                            "Y 轴标题（带单位，如'订单量（笔）'、'销售额（元）'）。"
                            "无需加万/k/M等缩放后缀，图表会自动格式化大数字。"
                        ),
                    },
                    "y_axis_label_2": {
                        "type": "string",
                        "description": (
                            "combo 双轴图右侧 Y 轴标题（中文带单位，如'增长率（%）'、'客单价（元）'）。"
                            "仅 combo 类型需要填写，其他图表类型不填。"
                        ),
                    },
                    "result_key": {
                        "type": "string",
                        "description": (
                            "指定用哪次查询的数据（对应 query_database 的 intent 参数）。"
                            "不填则用最近一次查询。跨轮对话时必须明确填写。"
                        ),
                    },
                    "format_options": {
                        "type": "object",
                        "properties": {
                            "sort_by": {
                                "type": "string",
                                "enum": ["x_asc", "x_desc", "y_asc", "y_desc", "none"],
                                "description": "排序方式，Top N 场景用 y_desc",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "只显示前 N 条",
                            },
                            "auto_format_large": {
                                "type": "boolean",
                                "description": "数值>10000时自动格式化为万，默认 true",
                            },
                        },
                    },
                    "insight": {
                        "type": "string",
                        "description": (
                            "图表解读（2-3句中文），必须基于实际数据。"
                            "包含：1.最显著趋势（量化） 2.第二个发现 3.业务含义或异常"
                        ),
                    },
                    "wordcloud_options": {
                        "type": "object",
                        "description": (
                            "词云图专用参数（chart_type='wordcloud' 时必填）。\n"
                            "⚠️ 用户要求词云图时，必须填此参数，不能省略。\n\n"
                            "两种输入模式二选一：\n"
                            "  模式A——已聚合（最常用）：query 结果已有词语列+频次列\n"
                            "    word_col = 词语列名（字符串列）\n"
                            "    freq_col = 频次/数量列名（数值列）\n"
                            "    示例：query 返回 [word, frequency] →\n"
                            "      wordcloud_options: {word_col: 'word', freq_col: 'frequency'}\n"
                            "    示例：query 返回 [product_category, order_count] →\n"
                            "      wordcloud_options: {word_col: 'product_category', freq_col: 'order_count'}\n\n"
                            "  模式B——原始文本：query 结果是未分词的长文本列\n"
                            "    text_col = 文本列名\n"
                            "    language = 'en'（英语/葡语）或 'zh'（中文）\n"
                            "    示例：query 返回 review_comment_message 列 →\n"
                            "      wordcloud_options: {text_col: 'review_comment_message', language: 'en'}"
                        ),
                        "properties": {
                            "text_col": {
                                "type": "string",
                                "description": "原始文本列名（与 word_col+freq_col 二选一）",
                            },
                            "word_col": {
                                "type": "string",
                                "description": "词语列名（已分词/已聚合场景，配合 freq_col 使用）",
                            },
                            "freq_col": {
                                "type": "string",
                                "description": "词频/数量列名（数值类型，配合 word_col 使用）",
                            },
                            "colormap": {
                                "type": "string",
                                "description": (
                                    "颜色方案，默认 viridis。"
                                    "可选：plasma / Blues / Reds / YlOrRd / coolwarm"
                                ),
                            },
                            "max_words": {
                                "type": "integer",
                                "description": "最多展示的词数，默认 80，上限 200",
                            },
                            "language": {
                                "type": "string",
                                "enum": ["auto", "zh", "en"],
                                "description": (
                                    "分词语言：auto 自动检测（推荐）/ zh 中文 / en 英文或其他语言"
                                ),
                            },
                        },
                    },
                    "bubble_options": {
                        "type": "object",
                        "description": (
                            "气泡图专用参数（chart_type='bubble' 时必填）。\n"
                            "必须提供 size_col；建议同时提供 label_col。\n"
                            "示例：各品类 avg_price（X）× avg_score（Y）× order_count（气泡大小）→\n"
                            "  bubble_options: {\"size_col\": \"order_count\", \"label_col\": \"category\", \"size_max\": 60}"
                        ),
                        "properties": {
                            "size_col": {
                                "type": "string",
                                "description": "控制气泡大小的数值字段名（必填）",
                            },
                            "label_col": {
                                "type": "string",
                                "description": "数据点名称列（字符串），悬停时显示为标题",
                            },
                            "size_max": {
                                "type": "integer",
                                "description": "最大气泡像素半径，默认 60，建议 30-100",
                            },
                            "color_col": {
                                "type": "string",
                                "description": "着色分组列（可选），按此列区分气泡颜色",
                            },
                        },
                    },
                    "force_chart_type": {
                        "type": "boolean",
                        "description": (
                            "是否强制使用 chart_type，跳过自动校验（不降级）。\n"
                            "当用户在提问中明确指定了图表类型时设为 true。\n"
                            "设为 true 时即使数据不适合该类型也会直接绘制。"
                        ),
                    },
                    "chart_source": {
                        "type": "string",
                        "enum": ["normal", "user_requested", "ai_recommended"],
                        "description": (
                            "图表来源标记，用于 UI 区分展示：\n"
                            "- 'user_requested'：用户明确要求的图表类型（配合 force_chart_type=true 使用）\n"
                            "- 'ai_recommended'：AI 认为更合适的推荐图表（在 user_requested 图之后额外调用）\n"
                            "- 'normal'：用户未指定类型，AI 正常选择（默认值）"
                        ),
                    },
                },
                "required": ["chart_type", "title", "insight"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_dataframe",
            "description": (
                "对已查询的数据做基础统计分析，以文字描述形式返回分析结果。"
                "必须先调用 query_database 才能使用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_type": {
                        "type": "string",
                        "description": (
                            "分析类型："
                            "describe（各列均值/标准差/百分位等描述统计）、"
                            "correlation（数值列两两相关性矩阵）、"
                            "groupby_summary（数值列与分类列的分组概览）"
                        ),
                        "enum": ["describe", "correlation", "groupby_summary"],
                    },
                    "result_key": {
                        "type": "string",
                        "description": "指定使用哪次查询的数据。不填则使用最近一次查询结果。",
                    },
                },
                "required": ["analysis_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_metric",
            "description": (
                "对一个指标的变化进行多维度归因分析。"
                "当用户问'为什么X指标变了''X指标下跌/上涨的原因''X指标变化归因'时使用。\n\n"
                "工具会自动完成：① 计算两期总体变化；② 各维度下钻，量化每个维度值的贡献度；"
                "③ 评估置信度；④ 生成中文归因结论。\n\n"
                "⚠️ 填写 filter_sql 时必须参考以下标准格式（DuckDB 语法）：\n"
                "- 月份范围: \"o.order_purchase_timestamp >= '2017-10-01' "
                "AND o.order_purchase_timestamp < '2018-01-01'\"\n"
                "- 季度: \"EXTRACT(YEAR FROM o.order_purchase_timestamp) = 2017 "
                "AND EXTRACT(QUARTER FROM o.order_purchase_timestamp) = 4\"\n"
                "- 整年: \"EXTRACT(YEAR FROM o.order_purchase_timestamp) = 2017\"\n"
                "- 自定义: \"o.order_purchase_timestamp BETWEEN '2017-10-01' AND '2017-12-31'\""
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_name": {
                        "type": "string",
                        "description": "要诊断的指标名，如'销售额'/'客单价'/'订单数'",
                    },
                    "base_sql": {
                        "type": "string",
                        "description": (
                            "指标的基础 SQL（包含 SELECT 聚合表达式和 FROM/JOIN，不含 WHERE）。"
                            "工具内部会自动拼接时间过滤条件。\n"
                            "聚合别名必须写 metric_value，例：\n"
                            "'SELECT SUM(oi.\"price\") as metric_value "
                            "FROM \"order_items\" oi "
                            "JOIN \"orders\" o ON oi.\"order_id\" = o.\"order_id\"'\n"
                            "注意：只写 SELECT 和 FROM/JOIN 部分，不要写 WHERE"
                        ),
                    },
                    "date_column": {
                        "type": "string",
                        "description": "时间字段的完整引用（含表别名），如 'o.order_purchase_timestamp'",
                    },
                    "period_a": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "时间段标签，如 '2017 Q3'",
                            },
                            "filter_sql": {
                                "type": "string",
                                "description": "时间过滤 SQL 片段（参考上方标准格式）",
                            },
                        },
                        "required": ["label", "filter_sql"],
                    },
                    "period_b": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "时间段标签，如 '2017 Q4'",
                            },
                            "filter_sql": {
                                "type": "string",
                                "description": "时间过滤 SQL 片段",
                            },
                        },
                        "required": ["label", "filter_sql"],
                    },
                    "drill_dimensions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dimension_name": {
                                    "type": "string",
                                    "description": "维度中文名，如 '品类' / '州' / '支付方式'",
                                },
                                "dimension_col": {
                                    "type": "string",
                                    "description": (
                                        "SQL 中的字段引用（含表别名），如 "
                                        "'t.product_category_name_english' / "
                                        "'o.customer_state'"
                                    ),
                                },
                                "extra_join": {
                                    "type": "string",
                                    "description": (
                                        "该维度需要的额外 JOIN（仅写 JOIN 子句，不含 WHERE）。"
                                        "如品类分析需要：'LEFT JOIN \"products\" p ON oi.\"product_id\" = p.\"product_id\" "
                                        "LEFT JOIN \"product_category_name_translation\" t "
                                        "ON p.\"product_category_name\" = t.\"product_category_name\"'"
                                    ),
                                },
                            },
                            "required": ["dimension_name", "dimension_col"],
                        },
                        "description": "要下钻的维度列表，建议 2-5 个（过多会导致响应缓慢）",
                    },
                    "decomposition_formula": {
                        "type": "string",
                        "description": (
                            "可选。指标分解公式，如 '销售额 = 订单数 × 客单价'。"
                            "提供后工具会先输出各子指标变化，帮助定位是量还是价驱动。"
                        ),
                    },
                },
                "required": [
                    "metric_name", "base_sql", "date_column",
                    "period_a", "period_b", "drill_dimensions",
                ],
            },
        },
    },
]


# ── 工具函数实现 ──────────────────────────────────────────────────────────────

def query_database(sql: str, intent: str, ds) -> str:
    """
    执行 SQL，把结果以 intent 为 key 缓存到 session_state['query_results']。

    返回给 LLM 的摘要采用动态截断策略：
    - 结果 ≤ 100 行：全量传给 LLM，Top 10/20/50 等排名查询零幻觉。
    - 结果 > 100 行：只传前 100 行，附注截断警告，提示 LLM 用 LIMIT/OFFSET 缩小范围。
    """
    if not sql or not sql.strip():
        return "错误: SQL 不能为空"

    try:
        df = ds.query(sql)

        if "query_results" not in st.session_state:
            st.session_state.query_results = {}

        st.session_state.query_results[intent] = {
            "df":        df,
            "sql":       sql,
            "intent":    intent,
            "timestamp": datetime.now().isoformat(),
            "row_count": len(df),
            "columns":   list(df.columns),
        }
        st.session_state.latest_query_key = intent

        MAX_FULL_ROWS = 100
        if df.empty:
            data_text = "（查询返回空结果）"
            suffix = ""
        elif len(df) <= MAX_FULL_ROWS:
            data_text = df.to_string(index=False)
            suffix = ""
        else:
            data_text = df.head(MAX_FULL_ROWS).to_string(index=False)
            suffix = (
                f"\n⚠️ 结果共 {len(df)} 行，已截断至前 {MAX_FULL_ROWS} 行。"
                f"如需查看特定排名范围，请在 SQL 中使用 LIMIT / OFFSET 控制返回行数。"
            )

        return (
            f"查询完成: {intent}\n"
            f"行数: {len(df)}\n"
            f"列: {', '.join(df.columns)}\n"
            f"数据:\n{data_text}{suffix}"
        )

    except ValueError as e:
        return f"查询失败: {e}"


def _apply_format_options(df: pd.DataFrame, x_col: str, y_col: str, fmt: dict) -> tuple[pd.DataFrame, str]:
    """
    按 format_options 对 DataFrame 排序、截断，并处理大数值格式化。
    返回 (处理后的 df, y_axis 单位后缀)。
    """
    sort_by = fmt.get("sort_by", "none")
    limit   = fmt.get("limit")
    auto_fmt = fmt.get("auto_format_large", True)

    if sort_by == "x_asc" and x_col in df.columns:
        df = df.sort_values(x_col, ascending=True)
    elif sort_by == "x_desc" and x_col in df.columns:
        df = df.sort_values(x_col, ascending=False)
    elif sort_by == "y_asc" and y_col in df.columns:
        df = df.sort_values(y_col, ascending=True)
    elif sort_by == "y_desc" and y_col in df.columns:
        df = df.sort_values(y_col, ascending=False)

    if limit and limit > 0:
        df = df.head(limit)

    # 不再做万单位缩放；轴刻度由 _apply_tick_format 统一格式化为 k/M/G
    _ = auto_fmt  # 保留参数避免调用方报错，但不使用
    return df.reset_index(drop=True), ""


# ── 多系列图表私有函数 ──────────────────────────────────────────────────────────

def _make_bar_multi(df, x_col, y_cols, title, x_label, y_label):
    """多系列分组柱状图（宽格式）。"""
    import plotly.express as px
    fig = px.bar(
        df, x=x_col, y=y_cols, title=title,
        barmode="group",
        labels={"value": y_label, "variable": "系列", x_col: x_label},
        color_discrete_sequence=COLOR_PALETTE,
    )
    fig.update_layout(legend_title_text="")
    return fig


def _make_barh_multi(df, x_col, y_cols, title, x_label, y_label):
    """多系列横向分组条形图（宽格式）。"""
    import plotly.express as px
    fig = px.bar(
        df, y=x_col, x=y_cols, title=title,
        barmode="group",
        orientation="h",
        labels={"value": x_label, "variable": "系列", x_col: y_label},
        color_discrete_sequence=COLOR_PALETTE,
    )
    fig.update_layout(legend_title_text="")
    return fig


def _make_line_multi(df, x_col, y_cols, title, x_label, y_label):
    """多系列折线图（宽格式）。"""
    import plotly.express as px
    fig = px.line(
        df, x=x_col, y=y_cols, title=title,
        markers=True,
        labels={"value": y_label, "variable": "系列", x_col: x_label},
        color_discrete_sequence=COLOR_PALETTE,
    )
    fig.update_traces(line=dict(width=2))
    fig.update_layout(legend_title_text="")
    return fig


def make_chart(
    chart_type: str,
    x_col: str = "",
    title: str = "图表",
    x_axis_label: str = "",
    y_axis_label: str = "",
    y_col: str = None,
    y_cols: list = None,
    y_axis_label_2: str = "",
    y_col_2: str = None,
    color_col: str = None,
    result_key: str = None,
    format_options: dict = None,
    insight: str = "",
    force_chart_type: bool = False,
    chart_source: str = "normal",
    wordcloud_options: dict = None,
    bubble_options: dict = None,
    _user_wants_wordcloud: bool = False,
) -> str:
    """
    绘制交互式图表，把 {fig, warning, insight, df} 存入 session_state['_agent_charts']。

    支持类型：line / bar / barh / pie / donut / scatter / heatmap / area / combo / table
    - 调用 validate_chart_type 校验，发生降级时记录 warning
    - 用 Plotly Express + Graph Objects 实现
    - app.py 在 run_agent 返回后统一渲染（含 warning / insight / 原始数据 expander）
    """
    try:
        import plotly.express as px
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return "错误: 缺少 plotly 库，请运行 pip install plotly"

    # ── 1. 获取数据 ───────────────────────────────────────────────────────────
    key = result_key or st.session_state.get("latest_query_key")
    if not key or key not in st.session_state.get("query_results", {}):
        return "错误: 没有可用的查询结果，请先调用 query_database"

    raw_df = st.session_state["query_results"][key]["df"]

    # ── 词云强制纠正（用户明确要词云但 LLM 写了 barh/bar）────────────────────────
    # 场景1：LLM 提供了 wordcloud_options 但 chart_type 写错
    if wordcloud_options and chart_type in ("bar", "barh"):
        chart_type = "wordcloud"
    # 场景2：LLM 完全没写 wordcloud_options，且 chart_type 是 barh/bar
    #        → 自动推断：找 string 列(词) + numeric 列(频次)
    if _user_wants_wordcloud and chart_type in ("bar", "barh") and not wordcloud_options:
        _str_cols = [c for c in raw_df.columns if raw_df[c].dtype == object]
        _num_cols = [c for c in raw_df.columns if pd.api.types.is_numeric_dtype(raw_df[c])]
        if _str_cols and _num_cols:
            chart_type = "wordcloud"
            wordcloud_options = {"word_col": _str_cols[0], "freq_col": _num_cols[0]}

    # ── 词云图：完全独立分支，不依赖 x_col/y_col 体系 ──────────────────────────
    if chart_type == "wordcloud":
        wc_opts = wordcloud_options or {}

        is_valid, msg = validate_wordcloud_input(raw_df, wc_opts)
        if not is_valid:
            return f"词云生成失败：{msg}"
        warn_msg = msg if msg else None     # 非空字符串为警告，不阻断生成

        try:
            png_bytes = chart_utils.render_wordcloud(
                df=raw_df,
                text_col=wc_opts.get("text_col"),
                word_col=wc_opts.get("word_col"),
                freq_col=wc_opts.get("freq_col"),
                title=title,
                colormap=wc_opts.get("colormap", "viridis"),
                max_words=int(wc_opts.get("max_words", 80)),
                language=wc_opts.get("language", "auto"),
            )
        except Exception as e:
            return f"词云生成失败：{e}"

        if "_agent_charts" not in st.session_state:
            st.session_state._agent_charts = []

        st.session_state._agent_charts.append({
            "chart_kind":   "wordcloud",
            "png_bytes":    png_bytes,
            "title":        title,
            "warning":      warn_msg,
            "insight":      insight,
            "df":           raw_df,
            "chart_source": chart_source,
        })
        return f"词云图已生成: {title}（数据来源: {key}）"

    # 判断系列模式
    is_multi = bool(y_cols)

    if not is_multi and not y_col:
        return "错误: 必须提供 y_col（单系列）或 y_cols（多系列）之一"

    if x_col not in raw_df.columns:
        return f"错误: 字段 '{x_col}' 不存在，可用字段: {list(raw_df.columns)}"

    if is_multi:
        missing = [c for c in y_cols if c not in raw_df.columns]
        if missing:
            return f"错误: y_cols 中以下字段不存在: {missing}，可用字段: {list(raw_df.columns)}"
        non_num = [c for c in y_cols if not pd.api.types.is_numeric_dtype(raw_df[c])]
        if non_num:
            return f"错误: y_cols 中以下字段不是数值类型: {non_num}"
    else:
        if y_col not in raw_df.columns:
            return f"错误: 字段 '{y_col}' 不存在，可用字段: {list(raw_df.columns)}"

    # ── 2. 图表类型校验 & 自动降级 ────────────────────────────────────────────
    # force_chart_type=True 时跳过校验（用户明确指定的类型，直接使用）
    if force_chart_type:
        final_type, warning = chart_type, None
    else:
        _y_for_validate = y_col if not is_multi else y_cols[0]
        final_type, warning = validate_chart_type(chart_type, raw_df, x_col, _y_for_validate,
                                                  y_cols=y_cols)

    # ── 3. 应用 format_options（在副本上操作，不污染缓存）──────────────────────
    fmt = format_options or {}
    _sort_ref = y_col if not is_multi else y_cols[0]
    chart_df, y_unit = _apply_format_options(raw_df.copy(), x_col, _sort_ref, fmt)

    # Y 轴标签追加单位后缀
    y_label = (y_axis_label + y_unit) if y_axis_label else y_unit or (y_col or "")
    x_label = x_axis_label or x_col

    # 公共布局参数
    layout_kwargs = dict(
        title_text=title,
        title_font_size=16,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Arial, sans-serif",
    )

    # ── 4. 绘图 ───────────────────────────────────────────────────────────────
    try:
        fig = None
        _bubble_quadrant_counts: dict = {}   # 仅气泡图使用，供 section 6 存入 chart dict

        if final_type == "bar":
            if is_multi:
                fig = _make_bar_multi(chart_df, x_col, y_cols, title, x_label, y_label)
            else:
                fig = px.bar(
                    chart_df, x=x_col, y=y_col, title=title,
                    color=color_col if color_col in chart_df.columns else None,
                    color_discrete_sequence=COLOR_PALETTE,
                    labels={x_col: x_label, y_col: y_label},
                )

        elif final_type == "barh":
            if is_multi:
                fig = _make_barh_multi(chart_df, x_col, y_cols, title, x_label, y_label)
            else:
                # barh 约定：x_col = 度量列（横向延伸），y_col = 分类列（垂直排列）
                # 防御：若 LLM 传反了（x_col 是字符串列、y_col 是数值列），自动对调
                _x_is_numeric = pd.api.types.is_numeric_dtype(chart_df[x_col])
                _y_is_numeric = pd.api.types.is_numeric_dtype(chart_df[y_col])
                if not _x_is_numeric and _y_is_numeric:
                    x_col, y_col = y_col, x_col
                    x_label, y_label = y_label, x_label
                fig = px.bar(
                    chart_df, x=x_col, y=y_col, title=title,
                    orientation="h",
                    color=color_col if color_col in chart_df.columns else None,
                    color_discrete_sequence=COLOR_PALETTE,
                    labels={x_col: x_label, y_col: y_label},
                )
                # total descending：度量最大的类别排在顶部，符合排名图习惯
                fig.update_layout(yaxis={"categoryorder": "total descending"})

        elif final_type == "line":
            if is_multi:
                fig = _make_line_multi(chart_df, x_col, y_cols, title, x_label, y_label)
            else:
                fig = px.line(
                    chart_df, x=x_col, y=y_col, title=title,
                    color=color_col if color_col in chart_df.columns else None,
                    color_discrete_sequence=COLOR_PALETTE,
                    markers=True,
                    labels={x_col: x_label, y_col: y_label},
                )

        elif final_type == "area":
            fig = px.area(
                chart_df, x=x_col, y=y_col, title=title,
                color=color_col if color_col in chart_df.columns else None,
                color_discrete_sequence=COLOR_PALETTE,
                labels={x_col: x_label, y_col: y_label},
            )

        elif final_type == "pie":
            fig = px.pie(
                chart_df, names=x_col, values=y_col, title=title,
                color_discrete_sequence=COLOR_PALETTE,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")

        elif final_type == "donut":
            fig = px.pie(
                chart_df, names=x_col, values=y_col, title=title,
                hole=0.45,
                color_discrete_sequence=COLOR_PALETTE,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")

        elif final_type == "scatter":
            fig = px.scatter(
                chart_df, x=x_col, y=y_col, title=title,
                color=color_col if color_col in chart_df.columns else None,
                color_discrete_sequence=COLOR_PALETTE,
                labels={x_col: x_label, y_col: y_label},
            )

        elif final_type == "heatmap":
            # color_col 明确指定值列；否则取第一个非 x/y 列作为 fallback
            other_cols = [c for c in chart_df.columns if c not in (x_col, y_col)]
            z_col = (
                color_col if (color_col and color_col in chart_df.columns)
                else (other_cols[0] if other_cols else None)
            )
            # 颜色方案：含负数（如环比%）用红绿双色，纯正数用蓝色渐变
            has_negative = z_col and pd.api.types.is_numeric_dtype(chart_df[z_col]) \
                           and (chart_df[z_col].dropna() < 0).any()
            color_scale = "RdYlGn" if has_negative else "Blues"
            try:
                if z_col:
                    pivot = chart_df.pivot_table(
                        index=y_col, columns=x_col,
                        values=z_col, aggfunc="sum",
                    )
                    # ── 鲁棒色阶：用 5th-95th 百分位截断，防止极端值劫持色阶 ──
                    flat = pd.Series(pivot.values.flatten()).dropna()
                    if has_negative and len(flat) > 0:
                        # 对称色阶，0 居中：取 5/95 分位的绝对值最大值作边界
                        q05 = float(flat.quantile(0.05))
                        q95 = float(flat.quantile(0.95))
                        bound = max(abs(q05), abs(q95))
                        zmin, zmax = -bound, bound
                    elif len(flat) > 0:
                        zmin = float(flat.quantile(0.05))
                        zmax = float(flat.quantile(0.95))
                    else:
                        zmin, zmax = None, None
                    fig = px.imshow(
                        pivot, title=title,
                        color_continuous_scale=color_scale, aspect="auto",
                        labels={"x": x_label, "y": y_label, "color": z_col},
                        text_auto=".1f",
                        zmin=zmin, zmax=zmax,
                    )
                else:
                    fig = px.density_heatmap(
                        chart_df, x=x_col, y=y_col, title=title,
                        color_continuous_scale=color_scale,
                        labels={x_col: x_label, y_col: y_label},
                    )
            except Exception:
                fig = px.density_heatmap(
                    chart_df, x=x_col, y=y_col, title=title,
                    color_continuous_scale="Blues",
                )

        elif final_type == "combo":
            # 双轴图：左轴柱状（y_col），右轴折线（y_col_2）
            if not y_col_2 or y_col_2 not in chart_df.columns:
                # 降级为普通柱状图
                warning = (warning or "") + (
                    f" combo 图需要 y_col_2 参数（当前缺失或字段不存在），已降级为柱状图"
                )
                fig = px.bar(
                    chart_df, x=x_col, y=y_col, title=title,
                    color_discrete_sequence=COLOR_PALETTE,
                )
            else:
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                fig.add_trace(
                    go.Bar(
                        x=chart_df[x_col], y=chart_df[y_col],
                        name=y_label or y_col,
                        marker_color=COLOR_PALETTE[0],
                        opacity=0.85,
                    ),
                    secondary_y=False,
                )
                fig.add_trace(
                    go.Scatter(
                        x=chart_df[x_col], y=chart_df[y_col_2],
                        name=y_col_2, mode="lines+markers",
                        line=dict(color=COLOR_PALETTE[1], width=2),
                        marker=dict(size=6),
                    ),
                    secondary_y=True,
                )
                fig.update_layout(title_text=title, **{k: v for k, v in layout_kwargs.items() if k != "title_text"})
                fig.update_yaxes(title_text=y_label, secondary_y=False)
                fig.update_yaxes(title_text=y_axis_label_2 or y_col_2, secondary_y=True, showgrid=False)
                fig.update_xaxes(title_text=x_label)
                _apply_tick_format(fig, axes=("y", "y2"))

        elif final_type == "table":
            header_vals = list(chart_df.columns)
            cell_vals   = [chart_df[c].tolist() for c in chart_df.columns]
            row_colors  = [
                ["#f0f4fb" if i % 2 == 0 else "white" for i in range(len(chart_df))]
                for _ in chart_df.columns
            ]
            fig = go.Figure(data=[go.Table(
                header=dict(
                    values=header_vals,
                    fill_color=COLOR_PALETTE[0],
                    font=dict(color="white", size=12),
                    align="left",
                    height=32,
                ),
                cells=dict(
                    values=cell_vals,
                    fill_color=row_colors,
                    align="left",
                    height=28,
                    font=dict(size=11),
                ),
            )])
            fig.update_layout(title_text=title, margin=dict(l=10, r=10, t=50, b=10))

        elif final_type == "bubble":
            bubble_opts = bubble_options or {}
            size_col    = bubble_opts.get("size_col")
            label_col   = bubble_opts.get("label_col")
            size_max    = bubble_opts.get("size_max", 60)
            color_col_b = bubble_opts.get("color_col", color_col)

            # 1. 参数校验
            if not size_col:
                return "错误: 气泡图需要指定 bubble_options.size_col（气泡大小字段）"
            if size_col not in chart_df.columns:
                return (
                    f"错误: size_col 字段 '{size_col}' 不存在，"
                    f"可用字段: {list(chart_df.columns)}"
                )

            # 2. 数值校验：size_col 包含非正数时自动偏移，不报错
            if (
                pd.api.types.is_numeric_dtype(chart_df[size_col])
                and chart_df[size_col].min() <= 0
            ):
                offset = abs(chart_df[size_col].min()) + 1
                chart_df = chart_df.copy()
                chart_df[size_col] = chart_df[size_col] + offset
                warning = (warning or "") + (
                    f" '{size_col}' 包含非正数值，已自动偏移 {offset} 以正常显示气泡"
                )

            # 3. hover_data：悬停时显示 X / Y / 气泡大小
            hover_data: dict = {}
            if pd.api.types.is_numeric_dtype(chart_df[x_col]):
                hover_data[x_col] = ":.2f"
            if pd.api.types.is_numeric_dtype(chart_df[y_col]):
                hover_data[y_col] = ":.2f"
            hover_data[size_col] = ":,"

            # 4. 绘制气泡图（px.scatter + size 参数）
            fig = px.scatter(
                chart_df,
                x=x_col,
                y=y_col,
                size=size_col,
                color=color_col_b if color_col_b and color_col_b in chart_df.columns else None,
                hover_name=label_col if label_col and label_col in chart_df.columns else None,
                hover_data=hover_data,
                size_max=size_max,
                title=title,
                labels={
                    x_col:    x_label,
                    y_col:    y_label,
                    size_col: f"气泡大小（{size_col}）",
                },
                color_discrete_sequence=COLOR_PALETTE,
            )

            # 5. 中位数参考线（必须显示，帮助用户定位象限）
            median_x = float(chart_df[x_col].median())
            median_y = float(chart_df[y_col].median())
            fig.add_vline(
                x=median_x, line_dash="dash", line_color="gray",
                annotation_text=f"中位数 {median_x:.1f}",
                annotation_position="top right",
            )
            fig.add_hline(
                y=median_y, line_dash="dash", line_color="gray",
                annotation_text=f"中位数 {median_y:.1f}",
                annotation_position="top right",
            )

            # 6. 象限统计（存入字典，供 app.py 渲染 expander；不在图内写文字以免拥挤）
            _bubble_quadrant_counts = {
                f"右上（高{x_col}·高{y_col}）": int(len(chart_df[
                    (chart_df[x_col] > median_x) & (chart_df[y_col] > median_y)
                ])),
                f"右下（高{x_col}·低{y_col}）": int(len(chart_df[
                    (chart_df[x_col] > median_x) & (chart_df[y_col] < median_y)
                ])),
                f"左上（低{x_col}·高{y_col}）": int(len(chart_df[
                    (chart_df[x_col] < median_x) & (chart_df[y_col] > median_y)
                ])),
                f"左下（低{x_col}·低{y_col}）": int(len(chart_df[
                    (chart_df[x_col] < median_x) & (chart_df[y_col] < median_y)
                ])),
            }

            fig.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )

        else:
            return f"不支持的图表类型: {final_type}"

        # ── 5. 统一应用布局（combo 已单独处理，跳过）──────────────────────────
        if final_type not in ("combo", "table"):
            fig.update_layout(**layout_kwargs)
            if final_type not in ("pie", "donut"):
                if final_type == "barh":
                    # barh：X 轴是度量，Y 轴是分类
                    fig.update_xaxes(title_text=x_label)
                    fig.update_yaxes(title_text=y_label)
                    _apply_tick_format(fig, axes=("x",))       # 度量在 X 轴
                elif final_type == "bubble":
                    # bubble：X、Y 两轴均为数值，都需要 k/M/G 格式化
                    fig.update_xaxes(title_text=x_label)
                    fig.update_yaxes(title_text=y_label)
                    _apply_tick_format(fig, axes=("x", "y"))
                else:
                    fig.update_xaxes(title_text=x_label)
                    fig.update_yaxes(title_text=y_label)
                    _apply_tick_format(fig, axes=("y",))       # 度量在 Y 轴
            fig.update_traces(
                selector={"type": "bar"},
                marker_line_width=0,
            )

        # ── 6. 存入 _agent_charts（含 warning / insight / 原始 df）─────────────
        if "_agent_charts" not in st.session_state:
            st.session_state._agent_charts = []

        chart_entry = {
            "fig":          fig,
            "title":        title,
            "warning":      warning,
            "insight":      insight,
            "df":           chart_df,
            "chart_source": chart_source,
        }
        if final_type == "bubble":
            chart_entry["chart_kind"]       = "bubble"
            chart_entry["quadrant_counts"]  = _bubble_quadrant_counts
        st.session_state._agent_charts.append(chart_entry)

        y_desc = ",".join(y_cols) if is_multi else y_col
        return (
            f"图表已生成: {title}"
            f"（最终类型={final_type}, X={x_col}, Y={y_desc}，数据来源: {key}）"
            + (f"\n⚠️ 类型已自动调整: {warning}" if warning else "")
        )

    except Exception as e:
        return f"图表生成失败: {e}"


def analyze_dataframe(analysis_type: str, result_key: str = None) -> str:
    """
    对缓存的查询结果做统计分析，返回文字描述给 LLM。
    """
    key = result_key or st.session_state.get("latest_query_key")
    if not key or key not in st.session_state.get("query_results", {}):
        return "错误: 没有可用的查询结果，请先调用 query_database"

    df = st.session_state["query_results"][key]["df"]

    try:
        if analysis_type == "describe":
            desc = df.describe(include="all").round(3).to_string()
            return f"【描述统计 - {key}】\n{desc}"

        elif analysis_type == "correlation":
            numeric_df = df.select_dtypes(include="number")
            if len(numeric_df.columns) < 2:
                return "数值列不足 2 列，无法计算相关性矩阵"
            corr = numeric_df.corr().round(3).to_string()
            return f"【相关性矩阵 - {key}】\n{corr}"

        elif analysis_type == "groupby_summary":
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            cat_cols     = df.select_dtypes(exclude="number").columns.tolist()
            lines = [
                f"【分组概览 - {key}】",
                f"总行数: {len(df)}，总列数: {len(df.columns)}",
                f"数值列 ({len(numeric_cols)}): {', '.join(numeric_cols) or '无'}",
                f"分类列 ({len(cat_cols)}): {', '.join(cat_cols) or '无'}",
            ]
            if numeric_cols:
                lines.append("\n数值列统计摘要（前6列）:")
                for col in numeric_cols[:6]:
                    s = df[col]
                    lines.append(
                        f"  {col}: 均值={s.mean():.2f}，最大={s.max():.2f}，"
                        f"最小={s.min():.2f}，非空={s.notna().sum()}"
                    )
            return "\n".join(lines)

        else:
            return f"不支持的分析类型: {analysis_type}"

    except Exception as e:
        return f"分析失败: {e}"


# ── diagnose_metric 私有辅助函数 ─────────────────────────────────────────────

def _split_base_sql(base_sql: str) -> tuple[str, str]:
    """
    把 base_sql 拆分为 (聚合SELECT表达式, FROM子句)。
    例：'SELECT SUM(price) as metric_value FROM order_items oi JOIN ...'
    → ('SUM(price) as metric_value', 'FROM order_items oi JOIN ...')
    """
    match = re.search(r"\bFROM\b", base_sql, re.IGNORECASE)
    if not match:
        raise ValueError("base_sql 必须包含 FROM 子句")
    select_expr = re.sub(r"^\s*SELECT\s+", "", base_sql[:match.start()], flags=re.IGNORECASE).strip()
    from_clause = base_sql[match.start():].strip()
    return select_expr, from_clause


def _run_sql(sql: str, ds) -> tuple[float | None, pd.DataFrame]:
    """执行 SQL，返回 (首行首数值列的值, 完整 DataFrame)。"""
    df = ds.query(sql)
    if df.empty:
        return None, df
    # 取第一个数值列作为指标值
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            val = df[col].iloc[0]
            return (float(val) if val is not None and not pd.isna(val) else None), df
    return None, df


def _run_dim_sql(sql: str, ds) -> pd.DataFrame:
    """执行维度 SQL，容错：执行失败返回空 DataFrame。"""
    try:
        return ds.query(sql)
    except Exception:
        return pd.DataFrame()


def _call_llm_for_conclusion(
    metric_name: str,
    overview: dict,
    top_contributors: list,
    dimension_results: list,
) -> str:
    """调用 DeepSeek 生成中文归因结论（3-5 句）。失败时返回占位文字。"""
    try:
        label_a = overview["period_a"]["label"]
        label_b = overview["period_b"]["label"]
        val_a   = overview["period_a"]["value"]
        val_b   = overview["period_b"]["value"]
        change  = overview["change"]
        chg_pct = overview["change_pct"]

        contrib_lines = "\n".join(
            f"  {i+1}. [{c['dimension']}] {c['value']}："
            f"变化 {c['change']:+.2f}，贡献度 {c['contribution_pct']:+.1f}%"
            for i, c in enumerate(top_contributors[:5])
        )
        prompt = (
            f"指标：{metric_name}\n"
            f"对比期：{label_a} vs {label_b}\n"
            f"{label_a} 值：{val_a:,.2f}，{label_b} 值：{val_b:,.2f}\n"
            f"变化：{change:+,.2f}（{chg_pct:+.1f}%）\n\n"
            f"Top 贡献因素（贡献度 = 该因素变化量 ÷ 总变化量）：\n{contrib_lines}\n\n"
            f"请用 3-5 句话给出数据分析结论，说明指标变化的主要原因，语言专业简洁。"
        )
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是资深数据分析师，用精炼的中文解释指标变化原因，聚焦关键归因，不罗列所有数字。"},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"（结论生成失败，原因：{e}）"


def _assess_confidence(
    change_pct: float,
    top_contribution_pct: float,
    period_a_value: float | None,
) -> tuple[str, list[str]]:
    """
    规则评估置信度（不依赖 LLM 自评）。

    规则：
    - 高：总变化 > 10% 且 Top 贡献因素占比 > 40%
    - 中：总变化 5-10%，或 Top 贡献不突出（20-40%）
    - 低：总变化 < 5%（可能是正常波动）或样本量过小

    返回 (confidence_label, limitations_list)
    """
    limitations = []
    abs_chg = abs(change_pct)
    abs_top = abs(top_contribution_pct)

    if abs_chg < 5:
        limitations.append(f"总变化幅度仅 {abs_chg:.1f}%，可能是正常业务波动而非显著趋势")
    if abs_top < 20:
        limitations.append("没有单一因素贡献度突出（< 20%），变化原因较分散，归因不确定性较高")
    if period_a_value is not None and abs(period_a_value) < 100:
        limitations.append("基期绝对值较小，百分比变化可能被放大，需结合绝对数值判断")
    if abs_top < 20 and abs_chg < 5:
        confidence = "低"
    elif abs_chg >= 10 and abs_top >= 40:
        confidence = "高"
    else:
        confidence = "中"

    if not limitations:
        limitations.append("归因覆盖了主要维度，但业务外因（促销、季节性、竞对）未纳入模型")

    return confidence, limitations


def diagnose_metric(
    metric_name: str,
    base_sql: str,
    date_column: str,
    period_a: dict,
    period_b: dict,
    drill_dimensions: list,
    decomposition_formula: str = None,
    ds=None,
) -> str:
    """
    多维度归因分析工具：量化各维度对指标变化的贡献，生成中文结论。

    Step 1 - 参数安全校验
    Step 2 - 计算两期总体指标值 & 变化
    Step 3 - 各维度下钻：分别查 A/B 期按维度分组数据，计算贡献度
    Step 4 - 汇总 Top 贡献因素（跨维度），评估置信度
    Step 5 - 调 LLM 生成中文归因结论
    Step 6 - 存入 session_state，返回格式化文字摘要给 LLM
    """
    # ── Step 1: 参数校验 ──────────────────────────────────────────────────────
    is_valid, err_msg = validate_diagnose_params(base_sql, period_a, period_b, drill_dimensions)
    if not is_valid:
        return f"❌ 参数校验失败: {err_msg}"

    try:
        agg_expr, from_clause = _split_base_sql(base_sql)
    except ValueError as e:
        return f"❌ base_sql 解析失败: {e}"

    # ── Step 2: 计算两期总体指标值 ─────────────────────────────────────────────
    sql_a = f"SELECT {agg_expr} FROM {from_clause[len('FROM'):].strip()} WHERE {period_a['filter_sql']}"
    sql_b = f"SELECT {agg_expr} FROM {from_clause[len('FROM'):].strip()} WHERE {period_b['filter_sql']}"

    try:
        value_a, _ = _run_sql(sql_a, ds)
        value_b, _ = _run_sql(sql_b, ds)
    except Exception as e:
        return f"❌ 总体指标查询失败: {e}\n\nSQL A:\n{sql_a}\n\nSQL B:\n{sql_b}"

    if value_a is None or value_b is None:
        return (
            f"❌ 查询返回空结果（A期={value_a}, B期={value_b}），"
            "请检查 base_sql 和 filter_sql 是否正确。"
        )

    total_change = value_b - value_a
    change_pct   = (total_change / abs(value_a) * 100) if value_a != 0 else float("inf")

    overview = {
        "period_a": {"label": period_a["label"], "value": value_a},
        "period_b": {"label": period_b["label"], "value": value_b},
        "change":     total_change,
        "change_pct": change_pct,
    }

    # ── Step 3: 各维度下钻 ────────────────────────────────────────────────────
    from_body = from_clause[len("FROM"):].strip()   # e.g. 'order_items oi JOIN orders o ON ...'
    dimension_results = []
    all_contributors  = []   # 汇总跨维度的贡献因素，后续取 Top N

    for dim in drill_dimensions:
        dim_name  = dim["dimension_name"]
        dim_col   = dim["dimension_col"]
        extra_j   = dim.get("extra_join", "")

        # 为品类维度自动追加 NULL 品类过滤（防止翻译表 NULL 污染排名）
        null_filter = ""
        if "product_category" in dim_col.lower():
            null_filter = " AND " + dim_col.split(" as ")[0].strip() + " IS NOT NULL"

        dim_sql_a = (
            f"SELECT {dim_col} as dimension_value, {agg_expr} "
            f"FROM {from_body} {extra_j} "
            f"WHERE {period_a['filter_sql']}{null_filter} "
            f"GROUP BY {dim_col} ORDER BY metric_value DESC"
        )
        dim_sql_b = (
            f"SELECT {dim_col} as dimension_value, {agg_expr} "
            f"FROM {from_body} {extra_j} "
            f"WHERE {period_b['filter_sql']}{null_filter} "
            f"GROUP BY {dim_col} ORDER BY metric_value DESC"
        )

        df_a = _run_dim_sql(dim_sql_a, ds)
        df_b = _run_dim_sql(dim_sql_b, ds)

        if df_a.empty and df_b.empty:
            dimension_results.append({
                "dimension_name": dim_name,
                "error": "两期均返回空结果，跳过该维度",
            })
            continue

        # 取数值列名（第 2 列，index=1）
        metric_col_a = df_a.columns[1] if len(df_a.columns) > 1 else None
        metric_col_b = df_b.columns[1] if len(df_b.columns) > 1 else None

        # 合并 A / B 期数据
        merged = pd.merge(
            df_a.rename(columns={metric_col_a: "val_a"}) if metric_col_a else df_a,
            df_b.rename(columns={metric_col_b: "val_b"}) if metric_col_b else df_b,
            on="dimension_value",
            how="outer",
        ).fillna(0)

        merged["val_a"] = pd.to_numeric(merged["val_a"], errors="coerce").fillna(0)
        merged["val_b"] = pd.to_numeric(merged["val_b"], errors="coerce").fillna(0)
        merged["dim_change"] = merged["val_b"] - merged["val_a"]
        merged["dim_change_pct"] = merged.apply(
            lambda r: (r["dim_change"] / abs(r["val_a"]) * 100) if r["val_a"] != 0 else (
                float("inf") if r["dim_change"] > 0 else (float("-inf") if r["dim_change"] < 0 else 0)
            ),
            axis=1,
        )
        # 贡献度 = 该维度值的变化量 / 总变化量绝对值 × 100%
        merged["contribution_pct"] = (
            merged["dim_change"] / abs(total_change) * 100
            if total_change != 0 else 0
        )
        # 按贡献度绝对值排序，最大影响排前面
        merged = merged.reindex(
            merged["contribution_pct"].abs().sort_values(ascending=False).index
        ).reset_index(drop=True)

        top_values = []
        for _, row in merged.head(10).iterrows():
            top_values.append({
                "value":            row["dimension_value"],
                "period_a_value":   round(row["val_a"], 2),
                "period_b_value":   round(row["val_b"], 2),
                "change":           round(row["dim_change"], 2),
                "change_pct":       round(float(row["dim_change_pct"]), 1)
                                    if not pd.isna(row["dim_change_pct"])
                                       and abs(row["dim_change_pct"]) < 1e9
                                    else None,
                "contribution_pct": round(float(row["contribution_pct"]), 1),
            })
            # 收集到全局贡献因素列表
            all_contributors.append({
                "dimension":        dim_name,
                "value":            row["dimension_value"],
                "change":           round(row["dim_change"], 2),
                "contribution_pct": round(float(row["contribution_pct"]), 1),
            })

        dimension_results.append({
            "dimension_name": dim_name,
            "dimension_col":  dim_col,
            "top_values":     top_values,
            "total_rows":     len(merged),
        })

    # ── Step 4: 汇总 Top 贡献因素 & 置信度 ──────────────────────────────────
    top_contributors = sorted(
        all_contributors,
        key=lambda x: abs(x["contribution_pct"]),
        reverse=True,
    )[:5]

    top1_pct = top_contributors[0]["contribution_pct"] if top_contributors else 0
    confidence, limitations = _assess_confidence(change_pct, top1_pct, value_a)

    # ── Step 5: LLM 生成归因结论 ─────────────────────────────────────────────
    conclusion = _call_llm_for_conclusion(metric_name, overview, top_contributors, dimension_results)

    # ── Step 6: 存入 session_state，格式化输出 ────────────────────────────────
    result_data = {
        "metric_name":       metric_name,
        "overview":          overview,
        "top_contributors":  top_contributors,
        "dimension_analysis": dimension_results,
        "conclusion":        conclusion,
        "confidence":        confidence,
        "limitations":       limitations,
        "timestamp":         datetime.now().isoformat(),
    }
    if "_diagnose_results" not in st.session_state:
        st.session_state._diagnose_results = []
    st.session_state._diagnose_results.append(result_data)

    # ── 格式化返回文字（给 LLM 阅读，LLM 再转述给用户）──────────────────────
    direction = "上涨" if total_change > 0 else "下跌"
    lines = [
        f"【{metric_name} 归因分析完成】",
        f"",
        f"■ 总体变化",
        f"  {period_a['label']}: {value_a:,.2f}",
        f"  {period_b['label']}: {value_b:,.2f}",
        f"  变化: {total_change:+,.2f}（{direction} {abs(change_pct):.1f}%）",
        f"  置信度: {confidence}",
        f"",
        f"■ Top 贡献因素（贡献度 = 该因素变化 ÷ 总变化）",
    ]
    for i, c in enumerate(top_contributors[:5], 1):
        lines.append(
            f"  {i}. [{c['dimension']}] {c['value']}："
            f"  变化 {c['change']:+,.2f}，贡献度 {c['contribution_pct']:+.1f}%"
        )

    lines.append(f"")
    lines.append(f"■ 各维度详情")
    for dim_res in dimension_results:
        if "error" in dim_res:
            lines.append(f"  【{dim_res['dimension_name']}】{dim_res['error']}")
            continue
        lines.append(f"  【{dim_res['dimension_name']}】Top 5：")
        for v in dim_res["top_values"][:5]:
            chg_pct_str = f"{v['change_pct']:+.1f}%" if v["change_pct"] is not None else "N/A"
            lines.append(
                f"    - {v['value']}: "
                f"{v['period_a_value']:,.2f} → {v['period_b_value']:,.2f}，"
                f"变化 {v['change']:+,.2f}（{chg_pct_str}），"
                f"贡献度 {v['contribution_pct']:+.1f}%"
            )

    if decomposition_formula:
        lines += ["", f"■ 指标分解公式: {decomposition_formula}", "  （如需各子指标拆解，请调用 query_database 分别查询各子指标）"]

    lines += [
        "",
        f"■ 归因结论",
        f"  {conclusion}",
        "",
        f"■ 局限性说明",
    ]
    for lim in limitations:
        lines.append(f"  • {lim}")

    return "\n".join(lines)


# ── 工具调度器 ────────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict, ds, user_wants_wordcloud: bool = False) -> str:
    """将 LLM 的 tool_call 路由到对应的工具函数。"""
    if name == "query_database":
        return query_database(
            sql=args.get("sql", ""),
            intent=args.get("intent", "未命名查询"),
            ds=ds,
        )
    elif name == "make_chart":
        return make_chart(
            chart_type=args.get("chart_type", "bar"),
            x_col=args.get("x_col", ""),
            y_col=args.get("y_col"),
            y_cols=args.get("y_cols"),
            title=args.get("title", "图表"),
            x_axis_label=args.get("x_axis_label", ""),
            y_axis_label=args.get("y_axis_label", ""),
            y_axis_label_2=args.get("y_axis_label_2", ""),
            y_col_2=args.get("y_col_2"),
            color_col=args.get("color_col"),
            result_key=args.get("result_key"),
            format_options=args.get("format_options"),
            insight=args.get("insight", ""),
            force_chart_type=args.get("force_chart_type", False),
            chart_source=args.get("chart_source", "normal"),
            wordcloud_options=args.get("wordcloud_options"),
            bubble_options=args.get("bubble_options"),
            _user_wants_wordcloud=user_wants_wordcloud,
        )
    elif name == "analyze_dataframe":
        return analyze_dataframe(
            analysis_type=args.get("analysis_type", "describe"),
            result_key=args.get("result_key"),
        )
    elif name == "diagnose_metric":
        return diagnose_metric(
            metric_name=args.get("metric_name", "指标"),
            base_sql=args.get("base_sql", ""),
            date_column=args.get("date_column", ""),
            period_a=args.get("period_a", {}),
            period_b=args.get("period_b", {}),
            drill_dimensions=args.get("drill_dimensions", []),
            decomposition_formula=args.get("decomposition_formula"),
            ds=ds,
        )
    else:
        known = "query_database, make_chart, analyze_dataframe, diagnose_metric"
        return f"未知工具: {name}，可用工具: {known}"
