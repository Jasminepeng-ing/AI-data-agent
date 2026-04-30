"""
src/app.py
==========
Streamlit 主程序：AI 数据分析 Agent 的用户界面。

启动方式（在项目根目录 AI-data-agent/ 下运行）：
    streamlit run src/app.py

页面结构：
    左侧 Sidebar ── 数据库 Schema 展示 + 文件上传
    右侧主区域 ── 聊天界面（输入框 + 对话历史）

Week 1 状态：LLM 尚未接入，用户输入会被 echo 回来。
Week 2 计划：将 handle_message() 替换为 DeepSeek API 调用。
"""

import os
import sys
import streamlit as st

# ── 路径处理 ──────────────────────────────────────────────────────────────────
# 把 src/ 加入模块搜索路径，确保无论从哪里启动都能 import data_source
SRC_DIR      = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
sys.path.insert(0, SRC_DIR)

from data_source import DataSource

# ── 常量 ──────────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(PROJECT_ROOT, "data", "olist.db")


# ── 页面基础配置（必须是第一个 Streamlit 调用）────────────────────────────────
st.set_page_config(
    page_title="AI 数据分析 Agent",
    page_icon="🤖",
    layout="wide",          # 宽屏布局，聊天区更宽敞
    initial_sidebar_state="expanded",
)

# 隐藏 file_uploader 内置的文件列表（含 × 按钮），只保留拖拽/选择区域
# 用 :has() 从有 testid 的子元素向上选中没有 testid 的 <li> 父行，整行隐藏
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
    """
    获取全局唯一的 DataSource 实例。

    用 @st.cache_resource 装饰：
      - Streamlit 每次用户操作都会重跑整个脚本
      - 这个装饰器确保数据库连接只建立一次，不会反复开关文件
      - 类比：就像单例模式，全局共享同一个连接

    Returns
    -------
    DataSource
        已连接好的数据源对象。连接失败时在页面显示错误并停止执行。
    """
    try:
        return DataSource(DB_PATH)
    except ConnectionError as e:
        st.error(f"❌ 数据库连接失败\n\n{e}")
        st.stop()  # 连接失败则停止渲染页面，避免后续报错


# ── 对话处理函数（Week 2 在这里接 LLM）──────────────────────────────────────
def handle_message(user_input: str, ds: DataSource) -> str:
    """
    处理用户输入，返回 Assistant 的回复文本。

    Week 1（当前）：直接 echo 用户输入。
    Week 2（计划）：把这个函数替换为 DeepSeek API 调用：
        1. 把 ds.get_schema() 注入 system prompt
        2. 把 st.session_state.messages 作为历史传入
        3. 让 LLM 生成 SQL → 调用 ds.query() → 返回结果

    Parameters
    ----------
    user_input : str
        用户在聊天框里输入的文字。
    ds : DataSource
        数据源对象，Week 2 用于执行 LLM 生成的 SQL。

    Returns
    -------
    str
        Assistant 要显示的回复文字。
    """
    # ── Week 1：简单 echo，让页面跑通 ──
    return f"你说的是：{user_input}"

    # ── Week 2 预留位置（注释保留，届时解注释并删掉上面一行）──
    # from llm_agent import run_agent
    # return run_agent(user_input, ds, st.session_state.messages)


# ── 初始化 Session State ──────────────────────────────────────────────────────
def init_session_state() -> None:
    """
    初始化 Streamlit session_state 中的所有状态变量。

    必须在页面渲染前调用，防止首次加载时 KeyError。

    对话历史格式与 DeepSeek / OpenAI API 一致：
        [{"role": "user",      "content": "..."},
         {"role": "assistant", "content": "..."}]
    Week 2 可以直接把这个列表传给 API 的 messages 参数。
    """
    if "messages" not in st.session_state:
        # 预置一条欢迎消息，让页面不显得空旷
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
        # 记录已上传的文件名 → 表名映射，Sidebar 展示用
        st.session_state.uploaded_tables = {}

    if "deleted_files" not in st.session_state:
        # 记录"用户主动点击🗑️删除"的文件名集合
        # 防止 rerun 时 uploader 里残留的文件被当作新文件重新注册
        st.session_state.deleted_files = set()


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar(ds: DataSource) -> None:
    """
    渲染左侧 Sidebar，包含两个区域：
      1. 数据库 Schema 展示（可折叠）
      2. 文件上传组件

    Parameters
    ----------
    ds : DataSource
        数据源对象，用于获取 schema 和注册上传文件。
    """
    with st.sidebar:
        st.title("📊 数据源管理")
        st.divider()

        # ── 区域 1：Schema 展示 ──────────────────────────────────────────────
        st.subheader("🗂️ 当前数据表")

        # 用 HTML 渲染两列表名：
        #   - 精确控制行距，避免 st.columns+caption 自带的大外边距
        #   - 超过 MAX_LEN 个字符的表名截断显示，鼠标悬浮时 tooltip 显示完整名
        tables = ds.list_tables()
        if tables:
            MAX_LEN = 19   # 超过此长度则截断

            def make_item(name: str) -> str:
                """生成单个表名的 HTML 块，含截断显示和 tooltip。"""
                display = name[:MAX_LEN] + "…" if len(name) > MAX_LEN else name
                return (
                    f'<div title="{name}" style="cursor:default;white-space:nowrap;'
                    f'padding:1px 0;">'
                    f'• {display}</div>'
                )

            # 用 CSS grid 代替 <table>，彻底避开 Streamlit 给表格加边框的问题
            items_html = "".join(make_item(t) for t in tables)
            st.markdown(
                f'<div style="display:grid;grid-template-columns:1fr 1fr;'
                f'font-size:0.85rem;color:rgb(120,120,130);line-height:1.6">'
                f'{items_html}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("（暂无可用数据表）")

        # Schema 详情用 expander 折叠，避免占满整个 Sidebar
        with st.expander("📋 查看完整字段结构", expanded=False):
            try:
                # 直接查 information_schema，逐表渲染，用 caption 小字显示
                # 表名和字段之间不插入空行，保持紧凑
                schema_df = ds.query("""
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'main'
                    ORDER BY table_name, ordinal_position
                """)
                for tname, group in schema_df.groupby("table_name", sort=True):
                    # 字段用 | 分隔，自动换行，不产生横向滚动
                    fields = " | ".join(
                        f"{r['column_name']} *({r['data_type']})*"
                        for _, r in group.iterrows()
                    )
                    # 表名加粗；字段紧跟其后，无空行
                    st.caption(f"**{tname}**")
                    st.caption(fields)
            except Exception as e:
                # 降级回纯文本
                st.caption(ds.get_schema())

        st.divider()

        # ── 区域 2：文件上传 ─────────────────────────────────────────────────
        st.subheader("📁 上传自定义数据")
        st.caption("支持 .csv 和 .xlsx 格式，可同时上传多个文件")

        # ── 已加载文件管理区（放在 uploader 上方，避免被拖拽区域覆盖导致按钮不可点）──
        # × 号：Streamlit 上传器自带，只从上传队列移除，数据仍在 DuckDB 中可查询
        # 🗑️ 号：真正从 DuckDB 卸载数据，文件彻底不可查询
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

        # ── 处理新增文件 ───────────────────────────────────────────────────────
        # 当文件从 uploader 里物理移除（用户点了 uploader 的 ×），
        # 同步清掉 deleted_files 里的记录，允许日后重新上传同名文件
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



# ── 主聊天区域 ────────────────────────────────────────────────────────────────
def render_chat(ds: DataSource) -> None:
    """
    渲染主区域的聊天界面，包含：
      - 历史消息展示
      - 底部输入框

    Parameters
    ----------
    ds : DataSource
        数据源对象，传递给 handle_message() 供后续 LLM 调用。
    """
    st.title("🤖 AI 数据分析 Agent")
    st.caption("基于 Olist 巴西电商数据集 | Powered by DuckDB + DeepSeek（Week 2 接入）")
    st.divider()

    # ── 渲染历史消息 ──────────────────────────────────────────────────────────
    for msg in st.session_state.messages:
        # avatar 参数设置头像：user 用人像，assistant 用机器人图标
        avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # ── 底部输入框 ────────────────────────────────────────────────────────────
    user_input = st.chat_input(
        placeholder="输入你的问题，例如：各州的订单量分布如何？"
    )

    # 用户提交输入后的处理流程
    if user_input:

        # 1. 把用户消息加入历史，并立即渲染到界面
        st.session_state.messages.append(
            {"role": "user", "content": user_input}
        )
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(user_input)

        # 2. 生成回复（Week 1 是 echo，Week 2 换成 LLM）
        with st.chat_message("assistant", avatar="🤖"):
            # spinner 让用户知道正在处理，Week 2 等待 API 响应时特别有用
            with st.spinner("思考中..."):
                try:
                    reply = handle_message(user_input, ds)
                except Exception as e:
                    reply = f"⚠️ 处理出错，请稍后重试。\n\n错误详情：{e}"

            st.markdown(reply)

        # 3. 把回复加入历史，下次 rerun 时能重新渲染
        st.session_state.messages.append(
            {"role": "assistant", "content": reply}
        )


# ── 程序入口 ──────────────────────────────────────────────────────────────────
def main() -> None:
    """
    App 主入口，按顺序执行：
      1. 初始化 session state
      2. 获取数据源
      3. 渲染 Sidebar
      4. 渲染聊天区域
    """
    init_session_state()
    ds = get_data_source()
    render_sidebar(ds)
    render_chat(ds)


if __name__ == "__main__":
    main()
