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
import sys
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


# ── 渲染单条历史消息 ───────────────────────────────────────────────────────────
def _render_message(msg: dict) -> None:
    """渲染一条历史消息，支持附带 SQL 折叠块和 DataFrame 结果表格。"""
    avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg.get("sql"):
            with st.expander("📋 查看 SQL", expanded=False):
                st.code(msg["sql"], language="sql")
        if msg.get("dataframe") is not None:
            st.dataframe(msg["dataframe"], use_container_width=True)


# ── 渲染待确认区块 ────────────────────────────────────────────────────────────
def _render_pending(ds: DataSource) -> None:
    """
    渲染"等待用户操作"的 SQL 确认 / 错误修复区块。

    两种状态：
      confirm → 展示 SQL + [确认执行] [取消]
      error   → 展示 SQL + 错误信息 + [让AI修复] [取消]
    """
    pending = st.session_state.pending

    with st.chat_message("assistant", avatar="🤖"):

        if pending["status"] == "confirm":
            st.markdown("我已根据你的问题生成了以下 SQL，**请确认后执行**：")
            with st.expander("📋 查看生成的 SQL", expanded=True):
                st.code(pending["sql"], language="sql")

            col_ok, col_cancel, _ = st.columns([1.2, 1, 5])
            with col_ok:
                if st.button("✅ 确认执行", type="primary", key="btn_confirm"):
                    try:
                        df = ds.query(pending["sql"])
                        st.session_state.messages.append({
                            "role":      "assistant",
                            "content":   f"查询完成，共返回 **{len(df):,} 行**数据。",
                            "sql":       pending["sql"],
                            "dataframe": df,
                        })
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
                                schema_text=ds.get_schema(),
                            )
                            new_sql = call_llm(fix_prompt)
                            pending["sql"]    = new_sql
                            pending["status"] = "confirm"
                            pending["error"]  = None
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

        # 调用 LLM 生成 SQL（spinner 期间页面锁定）
        with st.spinner("AI 正在分析问题并生成 SQL…"):
            try:
                user_prompt = build_nl2sql_prompt(user_input, ds.get_schema())
                sql = call_llm(user_prompt)
            except Exception as e:
                sql = ""
                api_error = str(e)
            else:
                api_error = ""

        if api_error:
            # API 调用本身失败（网络、密钥等）
            reply = f"⚠️ 调用 AI 失败，请稍后重试。\n\n错误详情：{api_error}"
            st.session_state.messages.append({"role": "assistant", "content": reply})
        elif not sql:
            # LLM 返回空串（判断无法用 SQL 回答）
            reply = "这个问题好像不是数据查询类问题，请换一个关于数据分析的问题，我来帮你生成 SQL 😊"
            st.session_state.messages.append({"role": "assistant", "content": reply})
        else:
            # SQL 生成成功，进入"待确认"状态
            st.session_state.pending = {
                "question": user_input,
                "sql":      sql,
                "status":   "confirm",
                "error":    None,
            }

        st.rerun()


# ── 程序入口 ──────────────────────────────────────────────────────────────────
def main() -> None:
    init_session_state()
    ds = get_data_source()
    render_sidebar(ds)
    render_chat(ds)


if __name__ == "__main__":
    main()
