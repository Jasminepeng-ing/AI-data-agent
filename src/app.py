"""
src/app.py
==========
Streamlit 主程序：AI 数据分析 Agent 的用户界面。

启动方式（在项目根目录 AI-data-agent/ 下运行）：
    streamlit run src/app.py

页面结构：
    左侧 Sidebar ── 数据源管理 + 本轮已执行查询（含撤销）+ 历史 SQL 记录
    右侧主区域 ── 聊天界面（Agent 进度 + 对话历史）

Week 2 架构：
    用户提问 → run_agent() 自动规划工具调用 → 展示 Agent 思考过程
    → 工具执行结果（查询/图表/分析）→ LLM 最终回答
    只有预估行数 > 10 万的查询才弹确认框（智能确认）。
"""

import os
import re
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

# ── 路径处理 ──────────────────────────────────────────────────────────────────
SRC_DIR      = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
sys.path.insert(0, SRC_DIR)

from data_source import DataSource, OLIST_BUILTIN_TABLES
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME, MAX_TOKENS
from prompts import build_fix_prompt
from agent import run_agent

# ── 常量 ──────────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(PROJECT_ROOT, "data", "olist.db")


# ── 页面基础配置（必须是第一个 Streamlit 调用）────────────────────────────────
st.set_page_config(
    page_title="AI 数据分析 Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 隐藏 file_uploader 内置的文件列表（含 × 按钮），只保留拖拽/选择区域
st.markdown(
    """
    <style>
    [data-testid="stFileUploaderFile"],
    li:has([data-testid="stFileUploaderFile"]),
    ul:has([data-testid="stFileUploaderFile"]) {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── 缓存数据库连接 ────────────────────────────────────────────────────────────
@st.cache_resource
def get_data_source() -> DataSource:
    try:
        return DataSource(DB_PATH)
    except ConnectionError as e:
        st.error(f"❌ 数据库连接失败\n\n{e}")
        st.stop()


# ── LLM 调用（仅用于 pending error 状态的 SQL 修复）──────────────────────────
def call_llm_for_fix(fix_prompt: str) -> str:
    """
    调用 DeepSeek 修复执行失败的 SQL。
    仅在大查询确认后执行出错时使用，正常查询路径通过 run_agent() 处理。
    """
    from openai import OpenAI
    from prompts import NL2SQL_SYSTEM_PROMPT

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": NL2SQL_SYSTEM_PROMPT},
            {"role": "user",   "content": fix_prompt},
        ],
        max_tokens=MAX_TOKENS,
        temperature=0,
    )
    return response.choices[0].message.content.strip()


# ── SQL 元信息解析（用于确认卡片）────────────────────────────────────────────
def _parse_sql_meta(sql: str) -> dict:
    """从 SQL 文本解析涉及的表名和是否包含 JOIN，用于确认卡片展示。"""
    pattern = r'(?:FROM|JOIN)\s+"?(\w+)"?'
    tables  = list(dict.fromkeys(re.findall(pattern, sql, re.IGNORECASE)))
    has_join = bool(re.search(r'\bJOIN\b', sql, re.IGNORECASE))
    return {"tables": tables, "has_join": has_join}


# ── 会话级隐藏机制辅助函数 ────────────────────────────────────────────────────

def get_hidden_tables() -> set:
    """获取当前会话中被隐藏的表名集合，无记录时返回空集合。"""
    return set(st.session_state.get("hidden_tables", set()))


def hide_table(table_name: str) -> None:
    """把单张表加入隐藏列表（不修改数据库）。"""
    if "hidden_tables" not in st.session_state:
        st.session_state["hidden_tables"] = set()
    st.session_state["hidden_tables"].add(table_name)


def hide_all_tables(data_source: DataSource) -> None:
    """隐藏当前所有可见表（含内置和上传）。绕过 list_tables 过滤，直接读 DuckDB 真实表列表。"""
    all_real_tables = _get_real_all_tables(data_source)
    st.session_state["hidden_tables"] = set(all_real_tables)


def hide_olist_tables(data_source: DataSource) -> None:
    """只隐藏 Olist 内置表，保留用户上传的表。"""
    if "hidden_tables" not in st.session_state:
        st.session_state["hidden_tables"] = set()
    all_real_tables = _get_real_all_tables(data_source)
    olist_to_hide = all_real_tables & OLIST_BUILTIN_TABLES
    st.session_state["hidden_tables"].update(olist_to_hide)


def _get_real_all_tables(data_source: DataSource) -> set:
    """直接从 DuckDB 获取所有实际存在的表（不经过 hidden 过滤），用于隐藏/恢复操作。"""
    try:
        rows = data_source.conn.execute("SHOW TABLES").fetchall()
        return {row[0] for row in rows}
    except Exception:
        return set()


def _sync_state_after_hide(hidden_table_names: list) -> None:
    """
    隐藏一批表后，清理 session_state 中引用了这些表的缓存。
    不清除 messages（保留对话历史）。
    """
    hidden_set = set(hidden_table_names)

    # 清理 query_results 中引用了被隐藏表的条目
    query_results = st.session_state.get("query_results", {})
    keys_to_remove = []
    for key, val in query_results.items():
        sql = val.get("sql", "").lower()
        for table in hidden_set:
            pattern = r"\b" + re.escape(table.lower()) + r"\b"
            if re.search(pattern, sql):
                keys_to_remove.append(key)
                break
    for key in keys_to_remove:
        query_results.pop(key, None)

    # 如果 latest_query_key 指向被移除的缓存，重置
    if st.session_state.get("latest_query_key") in keys_to_remove:
        st.session_state["latest_query_key"] = None

    # 清理 chart_registry 中基于被隐藏表数据的图表（用 caption 模糊匹配）
    chart_reg = st.session_state.get("chart_registry", [])
    st.session_state["chart_registry"] = [
        c for c in chart_reg
        if not any(table in c.get("caption", "").lower() for table in hidden_set)
    ]


def _insert_system_message(content: str) -> None:
    """在对话历史中插入一条 assistant 系统提示消息，告知用户数据状态变化。"""
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    st.session_state["messages"].append({"role": "assistant", "content": content})


def _format_row_count(n: int) -> str:
    """把数字格式化为易读字符串：99441 → '99.4K行'，1500000 → '1.5M行'。"""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M行"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}K行"
    return f"{n}行"


# ── 初始化 Session State ──────────────────────────────────────────────────────
def init_session_state() -> None:
    """
    初始化所有 session_state 变量。

    新增 Week 2 字段：
        query_results     : {intent -> {df, sql, intent, timestamp, row_count, columns}}
        latest_query_key  : str，最近一次 query_database 的 intent，供 make_chart 等默认使用
        _agent_charts     : list of {fig, title}，本轮 make_chart 生成的 Figure 暂存区

    pending 结构（Week 2 只在大查询时触发）：
        None                          → 无待处理任务
        {"question", "sql", "intent", "status": "confirm"/"error", "error", "estimated_rows"}
    """
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "你好！我是你的 AI 数据分析助手 🤖\n\n"
                    "我已加载 **Olist 巴西电商数据集**（9 张表，共约 150 万行数据）。\n\n"
                    "你可以在左侧查看数据表结构，也可以上传自己的 Excel / CSV 文件。\n\n"
                    "有什么想分析的，直接告诉我！"
                ),
            }
        ]

    if "uploaded_tables" not in st.session_state:
        st.session_state.uploaded_tables = {}

    if "deleted_files" not in st.session_state:
        st.session_state.deleted_files = set()

    if "pending" not in st.session_state:
        st.session_state.pending = None

    if "sql_history" not in st.session_state:
        st.session_state.sql_history = []  # [{question, sql}, ...]

    # Week 2 新增
    if "query_results" not in st.session_state:
        st.session_state.query_results = {}  # {intent -> {df, sql, ...}}

    if "latest_query_key" not in st.session_state:
        st.session_state.latest_query_key = None

    if "_agent_charts" not in st.session_state:
        st.session_state._agent_charts = []

    # Week 3 新增：图表注册表（供 generate_report 使用）+ 报告输出暂存
    if "chart_registry" not in st.session_state:
        st.session_state["chart_registry"] = []

    if "_report_output" not in st.session_state:
        st.session_state["_report_output"] = []

    # 会话级隐藏表集合（刷新页面后自动重置为空，底层数据库不变）
    if "hidden_tables" not in st.session_state:
        st.session_state["hidden_tables"] = set()


# ── 数据管理 Sidebar（新版：支持会话级隐藏）────────────────────────────────────
def render_data_management_sidebar(ds: DataSource) -> None:
    """
    渲染 Sidebar 的数据管理区域。
    包含：数据表列表（含×隐藏按钮）、两个批量隐藏按钮、字段详情、文件上传。
    """
    hidden = get_hidden_tables()
    table_infos = ds.get_table_info(hidden_tables=hidden)

    st.sidebar.markdown("**当前数据表**")

    # ── 1. 数据表列表 ─────────────────────────────────────────────────────────
    if not table_infos:
        st.sidebar.info(
            "📭 **当前无可见数据**\n\n"
            "所有数据表已在本次会话中隐藏。\n"
            "刷新页面可恢复所有数据。"
        )
    else:
        for info in table_infos:
            col_icon, col_name, col_meta, col_del = st.sidebar.columns(
                [0.25, 2.0, 1.8, 0.35]
            )
            with col_icon:
                icon = "🗄️" if info["type"] == "builtin" else "📄"
                st.write(icon)
            with col_name:
                st.write(f"**{info['name']}**")
            with col_meta:
                row_str = _format_row_count(info["row_count"])
                badge_color = "#1B3A6B" if info["type"] == "builtin" else "#E87722"
                badge_text = "内置" if info["type"] == "builtin" else "上传"
                st.markdown(
                    f'<span style="background:{badge_color};color:white;'
                    f'font-size:10px;padding:1px 6px;border-radius:3px;'
                    f'font-weight:600">{badge_text}</span> '
                    f'<span style="font-size:11px;color:#6B7280">{row_str}</span>',
                    unsafe_allow_html=True,
                )
            with col_del:
                is_uploaded = info["type"] == "uploaded"
                btn_help = (
                    f"在本次会话中删除表 {info['name']}"
                    if is_uploaded
                    else f"在本次会话中隐藏表 {info['name']}"
                )
                if st.button(
                    "×",
                    key=f"hide_table_{info['name']}",
                    help=btn_help,
                ):
                    if is_uploaded:
                        st.session_state["pending_delete_table"] = info["name"]
                    else:
                        st.session_state["pending_hide_table"] = info["name"]

    # ── 上传表删除确认（直接 unregister，不可通过刷新恢复）────────────────────
    pending_del = st.session_state.get("pending_delete_table")
    if pending_del:
        st.sidebar.warning(
            f"删除表 **{pending_del}**？\n\n"
            f"本次会话中将无法查询该表，刷新页面后也不会恢复。"
        )
        col_y, col_n = st.sidebar.columns(2)
        with col_y:
            if st.button(
                "确认删除",
                key="confirm_delete_single",
                type="primary",
                use_container_width=True,
            ):
                ds.unload_view(pending_del)
                st.session_state.get("uploaded_tables", {}).pop(
                    next(
                        (k for k, v in st.session_state.get("uploaded_tables", {}).items() if v == pending_del),
                        None,
                    ),
                    None,
                )
                _sync_state_after_hide([pending_del])
                st.session_state.pop("pending_delete_table", None)
                st.sidebar.toast(f"✅ {pending_del} 已删除")
                st.rerun()
        with col_n:
            if st.button(
                "取消", key="cancel_delete_single", use_container_width=True
            ):
                st.session_state.pop("pending_delete_table", None)
                st.rerun()

    # ── 内置表隐藏确认（session-level hiding，刷新后恢复）────────────────────
    pending = st.session_state.get("pending_hide_table")
    if pending:
        st.sidebar.warning(
            f"隐藏表 **{pending}**？\n\n"
            f"本次会话中将无法查询该表，刷新页面后恢复。"
        )
        col_y, col_n = st.sidebar.columns(2)
        with col_y:
            if st.button(
                "确认隐藏",
                key="confirm_hide_single",
                type="primary",
                use_container_width=True,
            ):
                hide_table(pending)
                _sync_state_after_hide([pending])
                st.session_state.pop("pending_hide_table", None)
                st.sidebar.toast(f"✅ {pending} 已在本会话中隐藏")
                st.rerun()
        with col_n:
            if st.button(
                "取消", key="cancel_hide_single", use_container_width=True
            ):
                st.session_state.pop("pending_hide_table", None)
                st.rerun()

    # ── 2. 字段详情展开 ───────────────────────────────────────────────────────
    if table_infos:
        with st.sidebar.expander("查看字段详情", expanded=False):
            for info in table_infos:
                st.markdown(f"**{info['name']}** （{info['col_count']} 列）")
                preview_cols = info["columns"][:6]
                more = info["col_count"] - 6
                suffix = f"…等 {info['col_count']} 列" if more > 0 else ""
                st.caption("、".join(preview_cols) + suffix)

    # ── 3. 两个批量隐藏按钮 ──────────────────────────────────────────────────
    st.sidebar.divider()
    col_all, col_olist = st.sidebar.columns(2)

    with col_all:
        all_disabled = len(table_infos) == 0
        if st.button(
            "🗑️ 清除所有",
            key="btn_hide_all",
            help="在本次会话中隐藏所有数据表（刷新后恢复）",
            disabled=all_disabled,
            use_container_width=True,
        ):
            st.session_state["confirm_hide_all"] = True

    with col_olist:
        visible_olist = [t for t in table_infos if t["type"] == "builtin"]
        olist_disabled = len(visible_olist) == 0
        if st.button(
            "📦 仅隐藏Olist",
            key="btn_hide_olist",
            help="只隐藏 Olist 内置数据，保留你上传的文件（刷新后恢复）",
            disabled=olist_disabled,
            use_container_width=True,
        ):
            st.session_state["confirm_hide_olist"] = True

    # ── 清除所有确认 ──────────────────────────────────────────────────────────
    if st.session_state.get("confirm_hide_all"):
        st.sidebar.warning("⚠️ 将隐藏所有数据表，包括你上传的文件")
        col_y, col_n = st.sidebar.columns(2)
        with col_y:
            if st.button(
                "确认", key="confirm_all_yes", type="primary", use_container_width=True
            ):
                names_before = [t["name"] for t in table_infos]
                hide_all_tables(ds)
                _sync_state_after_hide(names_before)
                _insert_system_message(
                    "🗑️ **所有数据表已在本次会话中隐藏。**\n\n"
                    "当前没有可查询的数据。请上传你的数据文件，\n"
                    "或刷新页面恢复 Olist 内置数据集。"
                )
                st.session_state.pop("confirm_hide_all", None)
                st.rerun()
        with col_n:
            if st.button("取消", key="confirm_all_no", use_container_width=True):
                st.session_state.pop("confirm_hide_all", None)
                st.rerun()

    # ── 仅隐藏 Olist 确认 ─────────────────────────────────────────────────────
    if st.session_state.get("confirm_hide_olist"):
        uploaded_count = len([t for t in table_infos if t["type"] == "uploaded"])
        st.sidebar.info(
            f"将隐藏 {len(visible_olist)} 张 Olist 内置表，\n"
            f"保留 {uploaded_count} 张上传文件"
        )
        col_y, col_n = st.sidebar.columns(2)
        with col_y:
            if st.button(
                "确认",
                key="confirm_olist_yes",
                type="primary",
                use_container_width=True,
            ):
                olist_names = [t["name"] for t in visible_olist]
                hide_olist_tables(ds)
                _sync_state_after_hide(olist_names)
                _insert_system_message(
                    "📦 **Olist 内置数据已在本次会话中隐藏。**\n\n"
                    "你上传的文件仍然可用。\n"
                    "刷新页面可恢复 Olist 数据。"
                )
                st.session_state.pop("confirm_hide_olist", None)
                st.rerun()
        with col_n:
            if st.button("取消", key="confirm_olist_no", use_container_width=True):
                st.session_state.pop("confirm_hide_olist", None)
                st.rerun()

    # ── 4. 已隐藏提示 ─────────────────────────────────────────────────────────
    if hidden:
        st.sidebar.caption(
            f"ℹ️ 本次会话已隐藏 {len(hidden)} 张表。刷新页面后自动恢复。"
        )

    # ── 5. 文件上传 ───────────────────────────────────────────────────────────
    st.sidebar.divider()
    uploaded_files = st.sidebar.file_uploader(
        "📁 上传数据文件",
        type=["xlsx", "csv"],
        accept_multiple_files=True,
        help="支持 Excel（.xlsx）和 CSV 文件，上传后立即可用",
    )
    if uploaded_files:
        newly_loaded = False
        for f in uploaded_files:
            existing_table = st.session_state.get("uploaded_tables", {}).get(f.name)
            # 已加载且当前可见（未隐藏）→ 跳过，避免重复注册
            if existing_table and existing_table not in get_hidden_tables():
                continue
            # 新文件，或同名文件曾被隐藏 → 重新注册（重新激活）
            try:
                table_name = ds.load_uploaded_file(f)
                if table_name:
                    if table_name in get_hidden_tables():
                        st.session_state["hidden_tables"].discard(table_name)
                    st.session_state.setdefault("uploaded_tables", {})[f.name] = table_name
                    newly_loaded = True
                    st.sidebar.success(f"✅ {f.name} → 表 `{table_name}`")
            except ValueError as e:
                st.sidebar.error(f"❌ 上传失败：{f.name}\n\n{e}")
        if newly_loaded:
            st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar(ds: DataSource) -> None:
    with st.sidebar:
        st.title("📊 数据源管理")

        # ── 清空对话按钮 ─────────────────────────────────────────────────────
        if st.button("🗑️ 清空对话", use_container_width=True, help="清空所有对话记录和本轮查询结果"):
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": (
                        "你好！我是你的 AI 数据分析助手 🤖\n\n"
                        "我已加载 **Olist 巴西电商数据集**（9 张表，共约 150 万行数据）。\n\n"
                        "你可以在左侧查看数据表结构，也可以上传自己的 Excel / CSV 文件。\n\n"
                        "有什么想分析的，直接告诉我！"
                    ),
                }
            ]
            st.session_state.query_results = {}
            st.session_state.latest_query_key = None
            st.session_state._agent_charts = []
            st.session_state.pending = None
            st.session_state["chart_registry"] = []
            st.session_state["_report_output"] = []
            st.rerun()

        st.divider()

        # ── 区域 1+2：数据表管理 + 文件上传（新版）──────────────────────────
        render_data_management_sidebar(ds)

        # ── 区域 3：历史 SQL 记录 ────────────────────────────────────────────
        if st.session_state.sql_history:
            st.divider()
            st.subheader("🕘 历史查询记录")
            st.caption("点击 ▶ 可重新提交到 Agent")
            for i, item in enumerate(st.session_state.sql_history):
                display = item["question"][:22] + "…" if len(item["question"]) > 22 else item["question"]
                col_q, col_btn = st.columns([5, 1])
                col_q.caption(f"• {display}")
                if col_btn.button("▶", key=f"hist_{i}", help=item["question"]):
                    st.session_state._replay_question = item["question"]
                    st.rerun()

        # ── 区域 4：本轮已执行查询（Week 2 新增，始终置于最底部）────────────
        query_results = st.session_state.get("query_results", {})
        if query_results:
            st.divider()
            st.subheader("🔎 已执行SQL记录")
            st.caption("Agent 本次会话中执行的查询，点击 📋 查看 SQL")

            # 按时间倒序展示（字典插入顺序即时间顺序）
            items = list(query_results.items())[::-1]
            for intent, info in items:
                display = intent[:20] + "…" if len(intent) > 20 else intent
                col_intent, col_detail = st.columns([5, 1])
                col_intent.caption(f"• {display}（{info['row_count']} 行）")
                with col_detail:
                    if st.button("📋", key=f"qr_{intent}", help=f"查看 SQL: {intent}"):
                        st.session_state._show_sql_for = intent
                        st.rerun()

            # 撤销最后一步查询
            if st.button("↩️ 撤销上一步查询", use_container_width=True):
                if items:
                    last_intent = items[0][0]
                    del st.session_state.query_results[last_intent]
                    remaining = list(st.session_state.query_results.keys())
                    st.session_state.latest_query_key = remaining[-1] if remaining else None
                    msgs = st.session_state.messages
                    for i in range(len(msgs) - 1, -1, -1):
                        if msgs[i]["role"] == "assistant":
                            msgs.pop(i)
                            break
                    st.rerun()

        # 展示被点击的 SQL（悬浮在 sidebar 内的 expander）
        show_sql_for = st.session_state.get("_show_sql_for")
        if show_sql_for and show_sql_for in query_results:
            with st.expander(f"📋 SQL: {show_sql_for}", expanded=True):
                st.code(query_results[show_sql_for]["sql"], language="sql")
                if st.button("关闭", key="close_sql_panel"):
                    st.session_state._show_sql_for = None
                    st.rerun()


# 列名中含以下关键词时，视为金额列，启用千位符
_AMOUNT_KEYWORDS = {
    "price", "value", "amount", "revenue", "payment", "cost", "fee",
    "income", "sales", "freight", "total", "receita", "valor", "preco",
    "金额", "价格", "收入", "费用", "成本", "总额", "货款",
}

# 列名含以下关键词时，合计行用算术均值（mean）
_AVG_KEYWORDS = {
    "avg", "average", "mean", "score", "rating",
    "均值", "平均", "评分", "分数",
}

# 列名含以下关键词时，合计行用中位数（median）
_MEDIAN_KEYWORDS = {"median", "中位数"}

# 列名含以下关键词时，合计行用众数（mode，取频次最高的值）
_MODE_KEYWORDS = {"mode", "众数"}

# 列名含以下关键词时，合计行用最大值
_MAX_KEYWORDS = {"max", "maximum", "最大值", "最大"}

# 列名含以下关键词时，合计行用最小值
_MIN_KEYWORDS = {"min", "minimum", "最小值", "最小"}

# 列名含以下关键词时，合计行显示"—"（比率/增速无法合计）
_RATIO_KEYWORDS = {
    "rate", "ratio", "pct", "percent", "proportion", "growth",
    "mom", "yoy", "change", "delta", "diff",
    "环比", "同比", "占比", "比率", "比例", "增速", "增幅", "变化",
}

# 所有"非求和"类关键词（用于决定首列标签）
_SPECIAL_AGG_KEYWORDS = (
    _AVG_KEYWORDS | _MEDIAN_KEYWORDS | _MODE_KEYWORDS
    | _MAX_KEYWORDS | _MIN_KEYWORDS
)


def _is_amount_col(col_name: str) -> bool:
    """列名（忽略大小写）含金额关键词则返回 True。"""
    lower = col_name.lower()
    return any(kw in lower for kw in _AMOUNT_KEYWORDS)


def _total_agg(col_name: str, series: pd.Series):
    """
    根据列名语义决定合计行的聚合方式（优先级从上到下匹配）：
    - 比率/增速类（环比/同比/pct/rate 等）→ "—"（无意义求和）
    - 中位数类（median/中位数）            → 实际中位数
    - 众数类（mode/众数）                  → 实际众数（频次最高值）
    - 最大值类（max/最大值）               → 实际最大值
    - 最小值类（min/最小值）               → 实际最小值
    - 均值类（avg/score/rating 等）        → 算术平均
    - 其他数值列                           → 求和
    """
    import math
    lower = col_name.lower()
    if any(kw in lower for kw in _RATIO_KEYWORDS):
        return float("nan")   # NaN 保持 float dtype；Styler 用 na_rep="—" 展示
    if any(kw in lower for kw in _MEDIAN_KEYWORDS):
        return round(series.median(), 4)
    if any(kw in lower for kw in _MODE_KEYWORDS):
        mode_vals = series.mode()
        return round(mode_vals.iloc[0], 4) if len(mode_vals) > 0 else float("nan")
    if any(kw in lower for kw in _MAX_KEYWORDS):
        return series.max()
    if any(kw in lower for kw in _MIN_KEYWORDS):
        return series.min()
    if any(kw in lower for kw in _AVG_KEYWORDS):
        return round(series.mean(), 4)
    return series.sum()


# ── 合计行辅助函数 ────────────────────────────────────────────────────────────
def _render_dataframe_with_total(df: pd.DataFrame) -> None:
    """
    将合计行直接拼接到主表末尾，渲染为同一个 st.dataframe 的最后一行。
    合计行用浅蓝背景高亮，下载时一并导出。

    聚合规则（按列名语义）：
    - 比率/增速类（环比/同比/pct/rate 等）→ "—"
    - 中位数类（median/中位数）            → 实际中位数
    - 众数类（mode/众数）                  → 实际众数
    - 最大值类（max/最大值）               → 实际最大值
    - 最小值类（min/最小值）               → 实际最小值
    - 均值类（avg/score/rating 等）        → 算术平均
    - 其他数值列                           → 求和
    """
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    float_cols   = df.select_dtypes(include="float").columns.tolist()
    int_cols     = df.select_dtypes(include=["int32", "int64", "int"]).columns.tolist()

    if not numeric_cols or len(df) <= 1:
        st.dataframe(df, use_container_width=True)
        return

    # 判断是否存在"非求和"类列，决定首列标签
    has_special_col = any(
        any(kw in c.lower() for kw in _SPECIAL_AGG_KEYWORDS) for c in numeric_cols
    )
    first_label = "合计 / 统计" if has_special_col else "合计"

    # 标签优先放入第一个非数值列，避免将字符串写入数值列导致 Arrow 序列化警告
    label_col = next((c for c in df.columns if c not in numeric_cols), None)

    total: dict = {}
    label_placed = False
    for i, col in enumerate(df.columns):
        if col == label_col:
            total[col] = first_label   # 第一个文本列：放标签
            label_placed = True
        elif i == 0 and not label_placed:
            total[col] = first_label   # 全数值列时退化为首列（保留原行为）
            label_placed = True
        elif col in numeric_cols:
            total[col] = _total_agg(col, df[col].dropna())
        else:
            total[col] = "—"
    total_df  = pd.DataFrame([total])
    combined  = pd.concat([df, total_df], ignore_index=True)

    # 若标签只能放在数值列（全数值 df），显式转 object 防止 Arrow 推断 int64 后报错
    if label_col is None:
        combined[df.columns[0]] = combined[df.columns[0]].astype(object)

    def _style_total(frame: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=frame.index, columns=frame.columns)
        styles.iloc[-1] = "background-color: #dbe4f5"
        return styles

    def _safe_float(is_amount: bool):
        if is_amount:
            return lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else str(x)
        return lambda x: f"{x:.2f}" if isinstance(x, (int, float)) and pd.notna(x) else str(x)

    def _safe_int_amount():
        return lambda x: f"{int(x):,}" if isinstance(x, (int, float)) and pd.notna(x) else str(x)

    fmt: dict = {}
    for col in float_cols:
        fmt[col] = _safe_float(_is_amount_col(col))
    for col in int_cols:
        if _is_amount_col(col):
            fmt[col] = _safe_int_amount()

    styled = (
        combined.style
        .apply(_style_total, axis=None)
        .format(fmt, na_rep="—")
    )

    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── 报告输出渲染 ─────────────────────────────────────────────────────────────
def _render_report_output(rpt: dict) -> None:
    """
    渲染 generate_report 工具产生的报告输出：
    - Markdown 内联展示
    - Word 下载按钮（.docx）
    - PDF 下载按钮（.pdf），失败时显示安装提示
    """
    title         = rpt.get("title", "分析报告")
    content       = rpt.get("content", "")
    output_format = rpt.get("output_format", "all")

    # 统一解析格式：支持 "all" / "markdown" / "word" / "pdf" / "word+pdf" 等复合格式
    if output_format == "all":
        fmts = {"markdown", "word", "pdf"}
    else:
        fmts = set(output_format.replace(",", "+").split("+"))

    st.divider()
    st.markdown(f"### 📄 报告：{title}")

    # Markdown 内联展示
    if "markdown" in fmts:
        with st.expander("📝 查看报告内容", expanded=True):
            st.markdown(content)

    # 下载按钮行（只在有 word 或 pdf 时才创建列布局）
    has_word = "word" in fmts
    has_pdf  = "pdf"  in fmts
    if has_word or has_pdf:
        col_word, col_pdf, _ = st.columns([1.5, 1.5, 4])

        if has_word:
            word_bytes = rpt.get("word_bytes")
            word_error = rpt.get("word_error")
            with col_word:
                if word_bytes:
                    st.download_button(
                        label="📄 下载 Word 报告",
                        data=word_bytes,
                        file_name=f"{title}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dl_word_{id(rpt)}",
                    )
                elif word_error:
                    st.error(f"Word 生成失败：{word_error}")

        if has_pdf:
            pdf_bytes = rpt.get("pdf_bytes")
            pdf_error = rpt.get("pdf_error")
            with col_pdf:
                if pdf_bytes:
                    chart_count = rpt.get("chart_count", 0)
                    st.download_button(
                        label="📑 下载 PDF 报告",
                        data=pdf_bytes,
                        file_name=f"{title}.pdf",
                        mime="application/pdf",
                        key=f"dl_pdf_{id(rpt)}",
                    )
                    if chart_count > 0:
                        st.caption(f"📊 本 PDF 包含本轮 {chart_count} 张图表截图")
                elif pdf_error:
                    st.error(f"PDF 生成失败：{pdf_error}")


# ── 快捷报告生成按钮 ──────────────────────────────────────────────────────────
def _render_report_button(msg: dict, msg_idx: int) -> None:
    """
    在有分析结果的 assistant 消息末尾渲染「生成分析报告」快捷区域。
    用户选择格式后点击确认，直接调用 generate_report 并将结果挂到该消息。
    """
    # 只对有工具调用、且尚未生成过报告的消息显示
    if not msg.get("tool_calls_log"):
        return
    if msg.get("report_outputs"):
        return

    kp = f"rptbtn_{msg_idx}"   # key prefix，保证每条消息唯一

    st.divider()
    with st.expander("📊 生成本次分析报告", expanded=False):
        st.caption("选择需要的报告格式，点击「确认生成」即可下载")
        c1, c2, c3 = st.columns(3)
        with c1:
            sel_md   = st.checkbox("📝 Markdown", value=True, key=f"{kp}_md")
        with c2:
            sel_word = st.checkbox("📄 Word",     value=True, key=f"{kp}_word")
        with c3:
            sel_pdf  = st.checkbox("📑 PDF",      value=True, key=f"{kp}_pdf")

        if st.button("✅ 确认生成", key=f"{kp}_confirm", type="primary"):
            # 收集选中格式
            fmts = []
            if sel_md:   fmts.append("markdown")
            if sel_word: fmts.append("word")
            if sel_pdf:  fmts.append("pdf")
            if not fmts:
                st.warning("请至少选择一种格式")
                return

            output_format = "all" if len(fmts) == 3 else "+".join(fmts)

            # 从该消息之前的对话中提取用户问题作为报告标题
            all_msgs = st.session_state.get("messages", [])
            user_q = ""
            for m in reversed(all_msgs[:msg_idx + 1]):
                if m.get("role") == "user" and m.get("content"):
                    user_q = m["content"][:50].strip().rstrip("。？?！!，,")
                    break
            report_title = f"{user_q}分析报告" if user_q else "本次分析报告"

            # 清空暂存区，调用 generate_report
            st.session_state["_report_output"] = []
            from tools import generate_report as _gen
            with st.spinner("正在生成报告，请稍候…"):
                _gen(
                    report_title=report_title,
                    include_sections=["背景", "核心发现", "详细分析", "建议", "附录"],
                    audience="operation",
                    output_format=output_format,
                    embed_charts=False,
                )

            # 把结果挂到本条消息
            rpts = list(st.session_state.get("_report_output", []))
            if rpts:
                st.session_state["messages"][msg_idx]["report_outputs"] = rpts
                st.session_state["_report_output"] = []
            st.rerun()


# ── 渲染单条历史消息 ───────────────────────────────────────────────────────────
def _render_message(msg: dict, msg_idx: int = -1) -> None:
    """
    渲染一条历史消息。

    Week 2 新增字段：
        tool_calls_log : [{tool_name, args, result}]，每个工具调用展示为折叠块
        charts         : [plotly Figure]，依次渲染图表
    """
    avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        if msg.get("question"):
            st.caption(f"📝 {msg['question']}")
        st.markdown(msg["content"])

        # ── Agent 工具调用记录（统一折叠到一个 expander）────────────────────
        tool_calls = msg.get("tool_calls_log") or []
        if tool_calls:
            with st.expander("📋 每一步分析及查询步骤详情", expanded=False):
                for i, step in enumerate(tool_calls, start=1):
                    tool_name   = step["tool_name"]
                    args        = step["args"]
                    result      = step["result"]
                    step_num    = step.get("step", i)  # 兼容旧消息（无 step 字段）
                    intent_hint = (
                        args.get("intent")
                        or args.get("title")
                        or args.get("analysis_type")
                        or tool_name
                    )
                    st.markdown(f"**第 {step_num} 步 🔧 {tool_name}: {intent_hint}**")
                    if args.get("sql"):
                        st.code(args["sql"], language="sql")
                    preview = result if len(result) <= 600 else result[:600] + "\n…（已截断）"
                    st.text(preview)
                    if i < len(tool_calls):
                        st.divider()

        # ── 兼容 Week 1 遗留的 sql 字段 ────────────────────────────────────
        if msg.get("sql"):
            with st.expander("📋 查看 SQL", expanded=False):
                st.code(msg["sql"], language="sql")

        # ── 查询结果 DataFrame ───────────────────────────────────────────────
        if msg.get("dataframe") is not None:
            _render_dataframe_with_total(msg["dataframe"])

        # ── 图表（Week 3：含 warning / insight / 原始数据 expander）──────────
        for i, chart in enumerate(msg.get("charts") or []):
            if isinstance(chart, dict):
                chart_kind   = chart.get("chart_kind", "plotly")
                fig          = chart.get("fig")
                warning      = chart.get("warning")
                insight      = chart.get("insight", "")
                df_raw       = chart.get("df")
                chart_source = chart.get("chart_source", "normal")

                # 来源标签（用户指定 / AI 推荐）
                if chart_source == "user_requested":
                    st.markdown("**📌 你要求的图表**")
                elif chart_source == "ai_recommended":
                    st.markdown("**💡 AI 推荐图表**（数据更适合此类型）")

                if chart_kind == "wordcloud":
                    # 词云图：st.image 渲染 + 下载按钮
                    png_bytes = chart.get("png_bytes")
                    if png_bytes:
                        st.image(png_bytes, caption=chart.get("title", ""),
                                 use_container_width=True)
                        st.download_button(
                            label="⬇️ 下载词云图 (PNG)",
                            data=png_bytes,
                            file_name=f"{chart.get('title', 'wordcloud')}.png",
                            mime="image/png",
                            key=f"wc_dl_{id(msg)}_{i}",
                        )
                elif chart_kind == "bubble":
                    # 气泡图：Plotly 渲染 + 象限分布 expander
                    if fig is not None:
                        st.plotly_chart(fig, use_container_width=True)
                    quadrant_counts = chart.get("quadrant_counts", {})
                    if quadrant_counts:
                        n_total = sum(quadrant_counts.values())
                        with st.expander("📊 象限分布统计", expanded=False):
                            for quadrant, count in quadrant_counts.items():
                                pct = count / n_total * 100 if n_total > 0 else 0
                                st.write(f"**{quadrant}**: {count} 个数据点（{pct:.1f}%）")
                else:
                    # 普通 Plotly 图表
                    if fig is not None:
                        st.plotly_chart(fig, use_container_width=True)

                if warning:
                    st.warning(f"⚠️ {warning}")
                if insight:
                    st.info(f"📊 **图表解读**\n\n{insight}")
                if df_raw is not None:
                    with st.expander("📋 查看原始数据", expanded=False):
                        st.dataframe(df_raw, use_container_width=True, hide_index=True)
            else:
                # 兼容 Week 2 旧格式（直接存 Figure 对象）
                st.plotly_chart(chart, use_container_width=True)

        # ── 报告输出（generate_report 工具生成）────────────────────────────────
        for rpt in msg.get("report_outputs") or []:
            _render_report_output(rpt)

        # ── 快捷报告按钮（仅 assistant 消息）───────────────────────────────
        if msg["role"] == "assistant" and msg_idx >= 0:
            _render_report_button(msg, msg_idx)


# ── 渲染待确认区块 ────────────────────────────────────────────────────────────
def _render_pending(ds: DataSource) -> None:
    """
    Week 2 的 pending 只在两种情况出现：
      confirm — Agent 检测到大数据量查询（> 10万行），暂停等用户确认
      error   — 大查询确认执行后 SQL 报错，可让 AI 修复
    """
    pending = st.session_state.pending

    with st.chat_message("assistant", avatar="🤖"):

        if pending["status"] == "confirm":
            st.markdown(
                "⚠️ 这个查询预估返回数据量较大，**请确认后再执行**："
            )

            st.markdown(f"**📝 查询意图：** {pending.get('intent', pending['question'])}")

            meta = _parse_sql_meta(pending["sql"])
            est  = pending.get("estimated_rows", -1)

            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**📋 涉及表：** {', '.join(meta['tables']) if meta['tables'] else '—'}")
            c2.markdown(f"**🔗 包含 JOIN：** {'是' if meta['has_join'] else '否'}")
            if est >= 0:
                c3.markdown(f"**📊 预估行数：** {est:,} 行")
            else:
                c3.markdown("**📊 预估行数：** 估算失败")

            with st.expander("📋 查看生成的 SQL", expanded=True):
                st.code(pending["sql"], language="sql")

            col_ok, col_cancel, _ = st.columns([1.2, 1, 5])
            with col_ok:
                if st.button("✅ 确认执行", type="primary", key="btn_confirm"):
                    try:
                        df      = ds.query(pending["sql"], hidden_tables=get_hidden_tables())
                        intent  = pending.get("intent", pending["question"])

                        # 存入 query_results，供后续工具引用
                        st.session_state.query_results[intent] = {
                            "df":        df,
                            "sql":       pending["sql"],
                            "intent":    intent,
                            "timestamp": datetime.now().isoformat(),
                            "row_count": len(df),
                            "columns":   list(df.columns),
                        }
                        st.session_state.latest_query_key = intent

                        st.session_state.messages.append({
                            "role":           "assistant",
                            "content":        f"（大数据量查询已确认）共返回 **{len(df):,} 行**数据。",
                            "question":       pending["question"],
                            "sql":            pending["sql"],
                            "dataframe":      df,
                            "tool_calls_log": [],
                            "charts":         [],
                        })
                        # 写入历史 SQL 记录（去重 + 最多 10 条）
                        entry = {"question": pending["question"], "sql": pending["sql"]}
                        history = st.session_state.sql_history
                        if entry not in history:
                            history.insert(0, entry)
                            if len(history) > 10:
                                history.pop()
                        st.session_state.pending = None
                    except ValueError as e:
                        pending["status"] = "error"
                        pending["error"]  = str(e)
                    st.rerun()

            with col_cancel:
                if st.button("❌ 取消", key="btn_cancel_confirm"):
                    st.session_state.pending = None
                    st.rerun()

        elif pending["status"] == "error":
            st.markdown("SQL 执行出错，可以让 AI 自动修复，或手动取消重新提问。")
            with st.expander("📋 查看 SQL（执行失败）", expanded=True):
                st.code(pending["sql"], language="sql")
            st.error(f"**错误信息：**\n\n```\n{pending['error']}\n```")

            col_fix, col_cancel, _ = st.columns([1.5, 1, 4])
            with col_fix:
                if st.button("🔧 让 AI 修复", type="primary", key="btn_fix"):
                    with st.spinner("AI 正在分析错误并修复 SQL…"):
                        try:
                            fix_prompt = build_fix_prompt(
                                original_sql=pending["sql"],
                                error_message=pending["error"],
                                user_question=pending["question"],
                                schema_text=ds.get_schema_with_relationships(),
                            )
                            new_sql = call_llm_for_fix(fix_prompt)
                            pending["sql"]            = new_sql
                            pending["status"]         = "confirm"
                            pending["error"]          = None
                            pending["estimated_rows"] = ds.estimate_row_count(new_sql)
                        except Exception as e:
                            st.error(f"修复失败：{e}")
                    st.rerun()

            with col_cancel:
                if st.button("❌ 取消", key="btn_cancel_error"):
                    st.session_state.pending = None
                    st.rerun()


# ── 主聊天区域 ────────────────────────────────────────────────────────────────
def render_chat(ds: DataSource) -> None:
    st.title("🤖 AI 数据分析 Agent")
    st.caption("基于 Olist 巴西电商数据集 | Powered by DuckDB + DeepSeek Function Calling")
    st.divider()

    # 1. 渲染历史消息
    for _msg_idx, msg in enumerate(st.session_state.messages):
        _render_message(msg, _msg_idx)

    # 2. 渲染待确认区块（仅大查询时触发）
    if st.session_state.pending:
        _render_pending(ds)

    # 3. 历史记录回放（sidebar ▶ 按钮触发）
    if "_replay_question" in st.session_state:
        replay_q = st.session_state["_replay_question"]
        del st.session_state["_replay_question"]  # 先删除，防止下次 rerun 重复触发
        st.session_state.messages.append({"role": "user", "content": replay_q})
        _run_and_store_agent(replay_q, ds)
        st.rerun()

    # 4. 底部输入框
    user_input = st.chat_input(
        placeholder="输入你的问题，例如：各州的订单量分布如何？"
    )

    if user_input:
        st.session_state.pending    = None
        st.session_state._agent_charts = []
        st.session_state.messages.append({"role": "user", "content": user_input})
        _run_and_store_agent(user_input, ds)
        st.rerun()


def _run_and_store_agent(user_input: str, ds: DataSource) -> None:
    """
    调用 run_agent()，把结果（回答、工具日志、图表）存入 session_state.messages。
    如果 Agent 检测到大查询，设置 pending 状态等待用户确认。

    独立抽取为函数是为了让 render_chat 和历史回放都能复用同一套逻辑。
    """
    # 清空本轮图表暂存区和报告暂存区
    st.session_state._agent_charts = []
    st.session_state["_report_output"] = []

    # 取历史（不含本轮 user 消息）
    history = st.session_state.messages[:-1]

    with st.status("🤖 Agent 正在分析...", expanded=True) as status_box:
        status_box.write("📖 读取问题，制定分析计划…")
        agent_result = run_agent(
            user_message=user_input,
            history=history,
            ds=ds,
            status_container=status_box,
        )
        if agent_result["needs_confirm"]:
            status_box.update(label="⏸️ 等待用户确认大数据量查询", state="running")
        else:
            status_box.update(label="✅ 分析完成", state="complete")

    if agent_result["needs_confirm"]:
        nc = agent_result["needs_confirm"]
        st.session_state.pending = {
            "question":       nc["question"],
            "sql":            nc["sql"],
            "intent":         nc.get("intent", nc["question"]),
            "status":         "confirm",
            "error":          None,
            "estimated_rows": nc["estimated_rows"],
        }
        return

    # AI 调用失败时不展示任何数据（否则会沿用上一问题的 query_results）
    # 注意：只有 run_agent 返回的系统级错误才算 is_error
    # LLM 在正文里写的 ⚠️ 警告（如幻觉报错）不属于系统错误，不能用 startswith 判断
    _final = agent_result["final_answer"]
    is_error = _final.startswith("⚠️ 调用 AI 失败") or _final.startswith("⚠️ Agent 超出最大工具调用次数")

    # 收集本轮 make_chart 生成的图表字典（含 fig / warning / insight / df）
    charts = (
        []
        if is_error
        else list(st.session_state.get("_agent_charts", []))
    )
    st.session_state._agent_charts = []

    # 收集本轮 generate_report 生成的报告输出
    report_outputs = (
        []
        if is_error
        else list(st.session_state.get("_report_output", []))
    )
    st.session_state["_report_output"] = []

    # ── 词云兜底：用户要词云但 LLM 没生成，直接用 render_wordcloud 补生成 ──────
    _WC_RE = re.compile(r'词云|word\s*cloud|wordcloud', re.IGNORECASE)
    if not is_error and _WC_RE.search(user_input):
        has_wc = any(c.get("chart_kind") == "wordcloud" for c in charts)
        if not has_wc:
            from chart_utils import render_wordcloud
            query_results = st.session_state.get("query_results", {})
            for _key, _info in reversed(list(query_results.items())):
                _df = _info["df"]
                if _df.empty:
                    continue
                _str_cols = [c for c in _df.columns if _df[c].dtype == object]
                _num_cols = [c for c in _df.columns if pd.api.types.is_numeric_dtype(_df[c])]
                try:
                    if _str_cols and _num_cols:
                        # 模式1：有词语列+频次列（category + count）
                        _png = render_wordcloud(
                            _df,
                            text_col=None,
                            word_col=_str_cols[0],
                            freq_col=_num_cols[0],
                            title="词云图",
                            language="auto",
                        )
                    elif _str_cols:
                        # 模式2：只有文本列（原始评论 / 文本内容）→ text_col 模式
                        _png = render_wordcloud(
                            _df,
                            text_col=_str_cols[0],
                            word_col=None,
                            freq_col=None,
                            title="词云图",
                            language="auto",
                        )
                    else:
                        continue
                    charts.append({
                        "chart_kind":   "wordcloud",
                        "png_bytes":    _png,
                        "title":        "词云图",
                        "insight":      "基于高频词汇自动生成的词云图。",
                        "df":           _df,
                        "chart_source": "user_requested",
                        "warning":      None,
                    })
                    break
                except Exception as _e:
                    print(f"[wordcloud fallback] error: {_e}")
                    continue

    # 取本轮最新查询结果，供 DataFrame 内联展示（失败时不取，避免显示上轮数据）
    latest_df = None
    if not is_error:
        latest_key = st.session_state.get("latest_query_key")
        if latest_key and latest_key in st.session_state.get("query_results", {}):
            latest_df = st.session_state["query_results"][latest_key]["df"]

    # 把 SQL 写入历史记录（失败时不写；取 tool_calls_log 里 query_database 的 SQL）
    for step in ([] if is_error else agent_result["tool_calls_log"]):
        if step["tool_name"] == "query_database":
            entry = {"question": user_input, "sql": step["args"].get("sql", "")}
            history_list = st.session_state.sql_history
            if entry not in history_list:
                history_list.insert(0, entry)
                if len(history_list) > 10:
                    history_list.pop()
            break  # 只记录第一个 SQL（多 SQL 场景后续版本再扩展）

    st.session_state.messages.append({
        "role":           "assistant",
        "content":        agent_result["final_answer"],
        "question":       user_input,
        "tool_calls_log": agent_result["tool_calls_log"],
        "dataframe":      latest_df,
        "charts":         charts,
        "report_outputs": report_outputs,
    })


# ── 程序入口 ──────────────────────────────────────────────────────────────────
def main() -> None:
    is_fresh_session = "uploaded_tables" not in st.session_state
    init_session_state()
    ds = get_data_source()
    if is_fresh_session:
        # 刷新页面 = 新 session，但 @cache_resource 的 DuckDB 连接跨刷新存活。
        # 主动清理上次会话注册的用户上传视图，确保刷新后只剩 Olist 9 张表。
        ds._cleanup_uploaded_tables()
    render_sidebar(ds)
    render_chat(ds)


if __name__ == "__main__":
    main()
