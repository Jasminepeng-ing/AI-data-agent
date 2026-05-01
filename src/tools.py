"""
src/tools.py
============
Agent 工具集：工具函数实现、Function Calling JSON Schema、工具调度器。

工具列表（Week 2）：
  1. query_database   — 执行 SQL，把结果缓存到 session_state['query_results'][intent]
  2. make_chart       — 用 Plotly Express 绘图，Figure 存入 session_state['_agent_charts']
  3. analyze_dataframe — 对缓存数据做描述统计 / 相关性 / 分组概览

设计原则：
  - 工具函数只写 session_state，不直接调用 st.write()，UI 渲染交给 app.py
  - 返回给 LLM 的始终是字符串摘要，不含完整 DataFrame（节省 token）
  - execute_tool() 是统一调度入口，agent.py 只调这一个函数
"""

from datetime import datetime
import streamlit as st


# ── Function Calling JSON Schema（发给 DeepSeek 的工具定义）────────────────────
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
                "对已查询的数据绘制图表。必须先调用 query_database 才能使用此工具。"
                "图表类型：bar（柱状图）、line（折线图）、pie（饼图）、scatter（散点图）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "description": "图表类型",
                        "enum": ["bar", "line", "pie", "scatter"],
                    },
                    "x_col": {
                        "type": "string",
                        "description": "X 轴字段名，必须是查询结果中存在的列名",
                    },
                    "y_col": {
                        "type": "string",
                        "description": "Y 轴字段名，必须是查询结果中的数值列",
                    },
                    "title": {
                        "type": "string",
                        "description": "图表标题（建议用中文，简洁明了）",
                    },
                    "result_key": {
                        "type": "string",
                        "description": (
                            "指定使用哪次查询的数据（即 query_database 的 intent 值）。"
                            "不填则自动使用最近一次查询结果。"
                        ),
                    },
                },
                "required": ["chart_type", "x_col", "y_col", "title"],
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
]


# ── 工具函数实现 ──────────────────────────────────────────────────────────────

def query_database(sql: str, intent: str, ds) -> str:
    """
    执行 SQL，把结果以 intent 为 key 缓存到 session_state['query_results']。

    返回给 LLM 的是文字摘要（行数 + 列名 + 前3行预览），不返回完整 DataFrame，
    避免占用大量 token。
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

        if df.empty:
            preview = "（查询返回空结果）"
        else:
            preview = df.head(3).to_string(index=False)

        return (
            f"查询完成: {intent}\n"
            f"行数: {len(df)}\n"
            f"列: {', '.join(df.columns)}\n"
            f"前3行预览:\n{preview}"
        )

    except ValueError as e:
        return f"查询失败: {e}"


def make_chart(
    chart_type: str,
    x_col: str,
    y_col: str,
    title: str,
    result_key: str = None,
) -> str:
    """
    用 Plotly Express 绘图，把 Figure 存入 session_state['_agent_charts']。

    app.py 在 run_agent 返回后取出 _agent_charts，附加到消息 dict 的 'charts' 字段，
    由 _render_message 统一渲染，确保历史消息回放时图表仍可显示。
    """
    try:
        import plotly.express as px
    except ImportError:
        return "错误: 缺少 plotly 库，请运行 pip install plotly"

    key = result_key or st.session_state.get("latest_query_key")
    if not key or key not in st.session_state.get("query_results", {}):
        return "错误: 没有可用的查询结果，请先调用 query_database"

    data_info = st.session_state["query_results"][key]
    df = data_info["df"]

    if x_col not in df.columns:
        return f"错误: 字段 '{x_col}' 不存在，可用字段: {list(df.columns)}"
    if y_col not in df.columns:
        return f"错误: 字段 '{y_col}' 不存在，可用字段: {list(df.columns)}"

    try:
        chart_makers = {
            "bar":     lambda: px.bar(df, x=x_col, y=y_col, title=title),
            "line":    lambda: px.line(df, x=x_col, y=y_col, title=title),
            "pie":     lambda: px.pie(df, names=x_col, values=y_col, title=title),
            "scatter": lambda: px.scatter(df, x=x_col, y=y_col, title=title),
        }
        if chart_type not in chart_makers:
            return f"不支持的图表类型: {chart_type}，可选: bar/line/pie/scatter"

        fig = chart_makers[chart_type]()

        if "_agent_charts" not in st.session_state:
            st.session_state._agent_charts = []
        st.session_state._agent_charts.append({"fig": fig, "title": title})

        return f"图表已生成: {title}（类型={chart_type}, X={x_col}, Y={y_col}，数据来源: {key}）"

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


# ── 工具调度器 ────────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict, ds) -> str:
    """
    将 LLM 的 tool_call 路由到对应的工具函数。

    agent.py 只调这一个函数，不直接调用具体工具，便于后续统一增减工具。
    """
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
            y_col=args.get("y_col", ""),
            title=args.get("title", "图表"),
            result_key=args.get("result_key"),
        )
    elif name == "analyze_dataframe":
        return analyze_dataframe(
            analysis_type=args.get("analysis_type", "describe"),
            result_key=args.get("result_key"),
        )
    else:
        known = "query_database, make_chart, analyze_dataframe"
        return f"未知工具: {name}，可用工具: {known}"
