"""
src/app.py
==========
Streamlit 主程序：AI 数据分析 Agent 的用户界面。

启动方式（在项目根目录 AI-data-agent/ 下运行）：
    streamlit run src/app.py

页面结构：
    左侧 Sidebar ── 数据库 Schema 展示 + 文件上传
    右侧主区域 ── 聊天界面（输入框 + 对话历史）

Week 2 状态：NL2SQL 已接入 DeepSeek，流程为：
    用户提问 → LLM 生成 SQL → 用户确认 → 执行 → 展示结果
"""

import os
import re
import sys
import pandas as pd
import streamlit as st

# ── 路径处理 ──────────────────────────────────────────────────────────────────
SRC_DIR      = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
sys.path.insert(0, SRC_DIR)

from data_source import DataSource
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME, MAX_TOKENS
from prompts import NL2SQL_SYSTEM_PROMPT, build_nl2sql_prompt, build_fix_prompt

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


# ── LLM 调用 ─────────────────────────────────────────────────────────────────
def call_llm(user_prompt: str) -> str:
    """
    调用 DeepSeek API，返回 LLM 的原始文本输出。

    始终使用 NL2SQL_SYSTEM_PROMPT 作为系统提示，
    temperature=0.1 保证 SQL 生成的确定性（低随机性）。
    """
    from openai import OpenAI

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": NL2SQL_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=MAX_TOKENS,
        temperature=0,
    )
    return response.choices[0].message.content.strip()


# ── SQL 执行策略 ──────────────────────────────────────────────────────────────
def should_confirm(sql: str, estimated_rows: int) -> bool:
    """
    判断是否需要向用户展示确认卡片再执行。

    Week 1：始终返回 True（所有查询都要确认）。

    Week 2 升级方式（只改这一处）：
        from config import LARGE_QUERY_ROW_THRESHOLD
        return estimated_rows < 0 or estimated_rows > LARGE_QUERY_ROW_THRESHOLD
        # estimated_rows=-1 表示估算失败，保守起见也要确认
    """
    return True


def _parse_sql_meta(sql: str) -> dict:
    """从 SQL 文本解析涉及的表名和是否包含 JOIN，用于确认卡片展示。"""
    pattern = r'(?:FROM|JOIN)\s+"?(\w+)"?'
    tables  = list(dict.fromkeys(re.findall(pattern, sql, re.IGNORECASE)))
    has_join = bool(re.search(r'\bJOIN\b', sql, re.IGNORECASE))
    return {"tables": tables, "has_join": has_join}


# ── 初始化 Session State ──────────────────────────────────────────────────────
def init_session_state() -> None:
    """
    初始化所有 session_state 变量。

    新增 pending：存储"已生成但等待用户确认"的中间状态。
    结构：
        None                          → 无待确认任务
        {
          "question": str,            → 用户原始问题
          "sql":      str,            → LLM 生成的 SQL（可被修复更新）
          "status":   "confirm"|"error",
          "error":    str | None,     → SQL 执行错误信息
        }
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
        st.session_state.sql_history = []  # 每项：{"question": str, "sql": str}


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar(ds: DataSource) -> None:
    with st.sidebar:
        st.title("📊 数据源管理")
        st.divider()

        # ── 区域 1：Schema 展示 ──────────────────────────────────────────────
        st.subheader("🗂️ 当前数据表")

        tables = ds.list_tables()
        if tables:
            MAX_LEN = 19

            def make_item(name: str) -> str:
                display = name[:MAX_LEN] + "…" if len(name) > MAX_LEN else name
                return (
                    f'<div title="{name}" style="cursor:default;white-space:nowrap;'
                    f'padding:1px 0;">'
                    f'• {display}</div>'
                )

            items_html = "".join(make_item(t) for t in tables)
            st.markdown(
                f'<div style="display:grid;grid-template-columns:1fr 1fr;'
                f'font-size:0.85rem;color:rgb(120,120,130);line-height:1.6">'
                f'{items_html}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("（暂无可用数据表）")

        with st.expander("📋 查看完整字段结构", expanded=False):
            try:
                schema_df = ds.query("""
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'main'
                    ORDER BY table_name, ordinal_position
                """)
                for tname, group in schema_df.groupby("table_name", sort=True):
                    fields = " | ".join(
                        f"{r['column_name']} *({r['data_type']})*"
                        for _, r in group.iterrows()
                    )
                    st.caption(f"**{tname}**")
                    st.caption(fields)
            except Exception:
                st.caption(ds.get_schema())

        st.divider()

        # ── 区域 2：文件上传 ─────────────────────────────────────────────────
        st.subheader("📁 上传自定义数据")
        st.caption("支持 .csv 和 .xlsx 格式，可同时上传多个文件")

        if st.session_state.uploaded_tables:
            st.caption("**已加载文件**（点击 🗑️ 可彻底删除数据）**：**")
            for fname, vname in list(st.session_state.uploaded_tables.items()):
                col_name, col_btn = st.columns([5, 1])
                display = fname[:22] + "…" if len(fname) > 22 else fname
                col_name.caption(f"• {display}")
                if col_btn.button("🗑️", key=f"del_{fname}", help=f"彻底删除「{fname}」的数据"):
                    ds.unload_view(vname)
                    del st.session_state.uploaded_tables[fname]
                    st.session_state.deleted_files.add(fname)
                    st.rerun()

        uploaded_files = st.file_uploader(
            label="选择文件",
            type=["csv", "xlsx"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        current_filenames = {f.name for f in uploaded_files} if uploaded_files else set()
        st.session_state.deleted_files = {
            f for f in st.session_state.deleted_files if f in current_filenames
        }

        newly_loaded = False
        if uploaded_files:
            for file in uploaded_files:
                if file.name in st.session_state.uploaded_tables:
                    continue
                if file.name in st.session_state.deleted_files:
                    continue
                try:
                    view_name = ds.load_uploaded_file(file)
                    st.session_state.uploaded_tables[file.name] = view_name
                    newly_loaded = True
                    st.markdown(
                        f'<div style="background:#d4edda;border:1px solid #c3e6cb;'
                        f'border-radius:4px;padding:5px 10px;'
                        f'font-size:0.75rem;color:#155724;line-height:1.5">'
                        f'✅ 已加载：{file.name} → 表名「{view_name}」</div>',
                        unsafe_allow_html=True,
                    )
                except ValueError as e:
                    st.error(f"❌ 上传失败：{file.name}\n\n{e}")

        if newly_loaded:
            st.rerun()

        # ── 区域 3：最近查询历史 ─────────────────────────────────────────────
        if st.session_state.sql_history:
            st.divider()
            st.subheader("🕘 最近查询")
            st.caption("点击 ▶ 可重新执行")
            for i, item in enumerate(st.session_state.sql_history):
                display = item["question"][:22] + "…" if len(item["question"]) > 22 else item["question"]
                col_q, col_btn = st.columns([5, 1])
                col_q.caption(f"• {display}")
                if col_btn.button("▶", key=f"hist_{i}", help=item["question"]):
                    try:
                        est = ds.estimate_row_count(item["sql"])
                    except Exception:
                        est = -1
                    st.session_state.pending = {
                        "question":      item["question"],
                        "sql":           item["sql"],
                        "status":        "confirm",
                        "error":         None,
                        "estimated_rows": est,
                    }
                    st.rerun()


# 列名中含以下关键词时，视为金额列，启用千位符
_AMOUNT_KEYWORDS = {
    "price", "value", "amount", "revenue", "payment", "cost", "fee",
    "income", "sales", "freight", "total", "receita", "valor", "preco",
    "金额", "价格", "收入", "费用", "成本", "总额", "货款",
}


def _is_amount_col(col_name: str) -> bool:
    """列名（忽略大小写）含金额关键词则返回 True。"""
    lower = col_name.lower()
    return any(kw in lower for kw in _AMOUNT_KEYWORDS)


# ── 合计行辅助函数 ────────────────────────────────────────────────────────────
def _render_dataframe_with_total(df: pd.DataFrame) -> None:
    """
    将合计行直接拼接到主表末尾，渲染为同一个 st.dataframe 的最后一行。
    合计行用浅蓝背景高亮，下载时一并导出。

    数字格式规则（优先级从高到低）：
      · 金额浮点列：千位符 + 2 位小数，如 25,000.00
      · 金额整数列：千位符，如 25,000
      · 普通浮点列：2 位小数，如 0.51
      · 普通整数列：原样显示

    跳过合计的情况：无数值列、结果仅 1 行（避免重复展示相同数值）。
    """
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    float_cols   = df.select_dtypes(include="float").columns.tolist()
    int_cols     = df.select_dtypes(include=["int32", "int64", "int"]).columns.tolist()

    if not numeric_cols or len(df) <= 1:
        st.dataframe(df, use_container_width=True)
        return

    # ① 构建合计行
    total: dict = {}
    for i, col in enumerate(df.columns):
        if i == 0:
            total[col] = "合计"
        elif col in numeric_cols:
            total[col] = df[col].sum()
        else:
            total[col] = "—"
    total_df = pd.DataFrame([total])

    # ② 拼接为单表（合计在最后一行）
    combined = pd.concat([df, total_df], ignore_index=True)

    # ③ 高亮合计行（最后一行浅蓝背景）
    def _style_total(frame: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=frame.index, columns=frame.columns)
        styles.iloc[-1] = "background-color: #dbe4f5"
        return styles

    # ④ 按列类型 + 是否金额列决定格式
    # 使用 callable formatter 而非格式字符串，避免合计行字符串值触发
    # "Cannot specify ',' with 's'" —— 字符串值直接原样返回
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


# ── 渲染单条历史消息 ───────────────────────────────────────────────────────────
def _render_message(msg: dict) -> None:
    """渲染一条历史消息，支持附带 SQL 折叠块和 DataFrame 结果表格。"""
    avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        if msg.get("question"):
            st.caption(f"📝 {msg['question']}")
        st.markdown(msg["content"])
        if msg.get("sql"):
            with st.expander("📋 查看 SQL", expanded=False):
                st.code(msg["sql"], language="sql")
        if msg.get("dataframe") is not None:
            _render_dataframe_with_total(msg["dataframe"])


# ── 渲染待确认区块 ────────────────────────────────────────────────────────────
def _render_pending(ds: DataSource) -> None:
    """
    渲染"等待用户操作"的 SQL 确认 / 错误修复区块。

    confirm 状态展示：查询意图 + 元信息卡片（表名、JOIN、预估行数）+ SQL + 按钮
    error   状态展示：SQL + 错误信息 + [让 AI 修复] [取消]
    """
    pending = st.session_state.pending

    with st.chat_message("assistant", avatar="🤖"):

        if pending["status"] == "confirm":
            st.markdown("我已根据你的问题生成了以下 SQL，**请确认后执行**：")

            # ── 查询意图 ───────────────────────────────────────────────────────
            st.markdown(f"**📝 查询意图：** {pending['question']}")

            # ── 元信息卡片 ─────────────────────────────────────────────────────
            meta = _parse_sql_meta(pending["sql"])
            est  = pending.get("estimated_rows", -1)

            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**📋 涉及表：** {', '.join(meta['tables']) if meta['tables'] else '—'}")
            c2.markdown(f"**🔗 包含 JOIN：** {'是' if meta['has_join'] else '否'}")
            if est >= 0:
                c3.markdown(f"**📊 预估行数：** {est:,} 行")
            else:
                c3.markdown("**📊 预估行数：** 估算失败")

            # ── SQL 预览 ───────────────────────────────────────────────────────
            with st.expander("📋 查看生成的 SQL", expanded=True):
                st.code(pending["sql"], language="sql")

            # ── 操作按钮 ───────────────────────────────────────────────────────
            col_ok, col_cancel, _ = st.columns([1.2, 1, 5])
            with col_ok:
                if st.button("✅ 确认执行", type="primary", key="btn_confirm"):
                    try:
                        df = ds.query(pending["sql"])
                        st.session_state.messages.append({
                            "role":      "assistant",
                            "content":   f"查询完成，共返回 **{len(df):,} 行**数据。",
                            "question":  pending["question"],
                            "sql":       pending["sql"],
                            "dataframe": df,
                        })
                        # 写入最近查询历史（去重 + 最多保留 10 条）
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
            st.markdown("SQL 执行出错，你可以让 AI 自动修复，或手动取消重新提问。")
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
                            new_sql = call_llm(fix_prompt)
                            pending["sql"]           = new_sql
                            pending["status"]        = "confirm"
                            pending["error"]         = None
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
    st.caption("基于 Olist 巴西电商数据集 | Powered by DuckDB + DeepSeek")
    st.divider()

    # 1. 渲染历史消息
    for msg in st.session_state.messages:
        _render_message(msg)

    # 2. 渲染待确认区块（如果有）
    if st.session_state.pending:
        _render_pending(ds)

    # 3. 底部输入框
    user_input = st.chat_input(
        placeholder="输入你的问题，例如：各州的订单量分布如何？"
    )

    if user_input:
        # 新问题到来，清除上一次未处理的 pending
        st.session_state.pending = None

        # 把用户消息写入历史
        st.session_state.messages.append({"role": "user", "content": user_input})

        # 调用 LLM 生成 SQL + 预估行数（同一 spinner 内完成）
        with st.spinner("AI 正在分析问题并生成 SQL…"):
            try:
                user_prompt = build_nl2sql_prompt(
                    user_input, ds.get_schema_with_relationships()
                )
                sql = call_llm(user_prompt)
            except Exception as e:
                sql = ""
                api_error = str(e)
            else:
                api_error = ""

            # 行数估算（LLM 成功后紧接着做，失败不阻断流程）
            estimated_rows = -1
            if sql and not api_error:
                try:
                    estimated_rows = ds.estimate_row_count(sql)
                except Exception:
                    estimated_rows = -1

        if api_error:
            reply = f"⚠️ 调用 AI 失败，请稍后重试。\n\n错误详情：{api_error}"
            st.session_state.messages.append({"role": "assistant", "content": reply})
        elif not sql:
            reply = "这个问题好像不是数据查询类问题，请换一个关于数据分析的问题，我来帮你生成 SQL 😊"
            st.session_state.messages.append({"role": "assistant", "content": reply})
        elif should_confirm(sql, estimated_rows):
            # 需要用户确认：进入 pending 状态
            st.session_state.pending = {
                "question":       user_input,
                "sql":            sql,
                "status":         "confirm",
                "error":          None,
                "estimated_rows": estimated_rows,
            }
        else:
            # Week 2 直接执行分支（当前 should_confirm 恒为 True，不会走到这里）
            try:
                df = ds.query(sql)
                st.session_state.messages.append({
                    "role":      "assistant",
                    "content":   f"查询完成，共返回 **{len(df):,} 行**数据。",
                    "sql":       sql,
                    "dataframe": df,
                })
            except ValueError as e:
                st.session_state.messages.append({
                    "role":    "assistant",
                    "content": f"❌ SQL 执行失败：{e}",
                })

        st.rerun()


# ── 程序入口 ──────────────────────────────────────────────────────────────────
def main() -> None:
    init_session_state()
    ds = get_data_source()
    render_sidebar(ds)
    render_chat(ds)


if __name__ == "__main__":
    main()
