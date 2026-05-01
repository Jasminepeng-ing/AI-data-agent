"""
src/data_source.py
==================
数据源抽象模块。

DataSource 类是整个项目的"数据门卫"：
  - 封装 DuckDB 连接的生命周期
  - 对外提供统一的 query / schema / 上传 接口
  - App 层和 LLM 层都通过这个类访问数据，不直接操作 DuckDB

设计原则：
  - 单一职责：只管"怎么拿数据"，不管"怎么展示数据"
  - 对 LLM 友好：get_schema() 输出格式专门为 prompt 优化
  - 对 Streamlit 友好：连接在 session 级别复用，避免重复开关文件
"""

import io
import os
import duckdb
import pandas as pd

# Olist 原始 9 张表，用于区分"系统表"和"用户上传表"
OLIST_TABLES = {
    "customers", "geolocation", "order_items", "order_payments",
    "order_reviews", "orders", "product_category_name_translation",
    "products", "sellers",
}

# Olist 数据集表关系说明，以 SQL 注释形式注入 prompt，帮助 LLM 正确编写 JOIN
OLIST_RELATIONSHIPS = [
    "-- orders 表通过 customer_id 关联 customers 表",
    "-- orders 表通过 order_id 关联 order_items 表（一对多）",
    "-- orders 表通过 order_id 关联 order_payments 表（一对多）",
    "-- orders 表通过 order_id 关联 order_reviews 表（一对多）",
    "-- order_items 表通过 product_id 关联 products 表",
    "-- order_items 表通过 seller_id 关联 sellers 表",
    "-- products 表通过 product_category_name 关联 product_category_name_translation 表",
    "-- customers 表通过 customer_zip_code_prefix 关联 geolocation 表（字段名为 geolocation_zip_code_prefix）",
    "-- sellers 表通过 seller_zip_code_prefix 关联 geolocation 表（字段名为 geolocation_zip_code_prefix）",
]


class DataSource:
    """
    封装 DuckDB 连接，提供数据查询、schema 获取、文件上传等功能。

    典型用法（在 Streamlit app 里）：
        ds = DataSource("data/olist.db")
        df = ds.query("SELECT * FROM orders LIMIT 10")
        schema_text = ds.get_schema()
    """

    def __init__(self, db_path: str) -> None:
        """
        初始化数据源，建立 DuckDB 连接。

        Parameters
        ----------
        db_path : str
            DuckDB 数据库文件的路径，例如 "data/olist.db"。
            如果文件不存在，DuckDB 会自动创建（空库）。

        Raises
        ------
        ConnectionError
            当数据库文件无法连接时抛出，附带友好提示信息。
        """
        self.db_path = db_path

        try:
            self.conn = duckdb.connect(db_path, read_only=False)
        except Exception as e:
            raise ConnectionError(
                f"无法连接到数据库 '{db_path}'。\n"
                f"请先运行 scripts/init_db.py 初始化数据库。\n"
                f"原始错误: {e}"
            )

        # 启动时清理遗留的用户上传表（上次会话用 CREATE TABLE 写入 olist.db 的残留）
        self._cleanup_uploaded_tables()

    # ── 核心查询 ──────────────────────────────────────────────────────────────

    def query(self, sql: str) -> pd.DataFrame:
        """
        执行 SQL 查询，返回 pandas DataFrame。

        这是整个项目最核心的方法：
          - Week 1：App 直接调用做演示
          - Week 2：LLM 生成的 SQL 字符串通过这里执行
          - Week 3：支持用户上传文件后的自定义查询

        Parameters
        ----------
        sql : str
            合法的 DuckDB SQL 语句。

        Returns
        -------
        pd.DataFrame
            查询结果。如果查询无结果，返回空 DataFrame。

        Raises
        ------
        ValueError
            当 SQL 执行出错时抛出，错误信息包含原始 SQL 和数据库报错，
            方便调试和向用户展示。
        """
        if not sql or not sql.strip():
            raise ValueError("SQL 语句不能为空。")

        try:
            result = self.conn.execute(sql).fetchdf()
            return result
        except Exception as e:
            raise ValueError(
                f"SQL 执行失败。\n"
                f"SQL: {sql}\n"
                f"错误: {e}"
            )

    # ── Schema 信息 ───────────────────────────────────────────────────────────

    def get_schema(self) -> str:
        """
        返回所有表的 schema 文本，格式专为 LLM prompt 设计。

        输出示例：
            表名: orders
            字段: order_id (VARCHAR), customer_id (VARCHAR), order_status (VARCHAR), ...

            表名: order_items
            字段: order_id (VARCHAR), order_item_id (INTEGER), product_id (VARCHAR), ...

        设计说明：
            - 每张表一段，表名和字段各占一行，便于 LLM 快速解析
            - 不包含行数统计（节省 token），行数可用 list_tables() 单独获取
            - Week 2 直接将此文本插入 system prompt 的 "数据库结构" 部分

        Returns
        -------
        str
            所有表的 schema 拼接文本。如果没有任何表，返回提示字符串。
        """
        try:
            # 从 information_schema 获取所有用户表的字段信息
            # 排除 DuckDB 内置的 system schema
            df = self.conn.execute("""
                SELECT
                    table_name,
                    column_name,
                    data_type
                FROM information_schema.columns
                WHERE table_schema = 'main'
                ORDER BY table_name, ordinal_position
            """).fetchdf()

            if df.empty:
                return "（当前数据库中没有任何表）"

            # 按表名分组，拼接成易读的文本格式
            lines = []
            for table_name, group in df.groupby("table_name", sort=True):
                # 每个字段格式：字段名 (类型)
                cols = ", ".join(
                    f"{row['column_name']} ({row['data_type']})"
                    for _, row in group.iterrows()
                )
                lines.append(f"表名: {table_name}")
                lines.append(f"字段: {cols}")
                lines.append("")  # 表与表之间空一行，提升可读性

            return "\n".join(lines).strip()

        except Exception as e:
            # schema 查询失败不应让整个 App 崩溃，返回降级文本
            return f"（获取 schema 失败: {e}）"

    # ── 表名列表 ──────────────────────────────────────────────────────────────

    def list_tables(self) -> list[str]:
        """
        返回当前数据库中所有可查询的表名（含通过上传注册的临时视图）。

        用途：
          - Sidebar 展示"当前可用数据源"
          - Week 2 可以让 LLM 先确认表名再生成 SQL，减少幻觉

        Returns
        -------
        list[str]
            表名列表，按字母排序。出错时返回空列表。
        """
        try:
            df = self.conn.execute("""
                SELECT DISTINCT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
            """).fetchdf()

            return df["table_name"].tolist()

        except Exception as e:
            # 返回空列表而非抛出异常，让调用方可以安全处理
            print(f"[DataSource] list_tables 失败: {e}")
            return []

    # ── 文件上传 ──────────────────────────────────────────────────────────────

    def load_uploaded_file(self, file) -> str:
        """
        将 Streamlit 上传的 CSV 或 Excel 文件注册为 DuckDB 临时视图。

        "临时视图"的含义：
          - 数据存在 pandas DataFrame 内存里，不写入 .db 文件
          - 重启 App / 刷新页面后自动消失
          - 同名文件重新上传会自动覆盖

        Parameters
        ----------
        file : streamlit.runtime.uploaded_file_manager.UploadedFile
            Streamlit file_uploader 返回的文件对象。
            支持 .csv 和 .xlsx 两种格式。

        Returns
        -------
        str
            注册成功的视图名（即表名），调用方可以直接用这个名字查询。

        Raises
        ------
        ValueError
            当文件格式不支持，或文件内容无法解析时抛出。
        """
        filename = file.name
        # 取文件名（不含后缀）作为视图名，空格替换为下划线
        view_name = os.path.splitext(filename)[0].replace(" ", "_")

        try:
            file_bytes = file.read()  # 读取上传内容为字节流

            # 根据扩展名选择 pandas 解析方式
            if filename.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(file_bytes))

            elif filename.endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(file_bytes))

            else:
                raise ValueError(
                    f"不支持的文件格式: {filename}\n"
                    f"目前支持 .csv 和 .xlsx 格式。"
                )

            # 先清理同名旧条目，防止重复
            self._unregister_view(view_name)

            # 纯内存注册：DataFrame 直接挂载为可查询的虚拟表
            # 不写入 olist.db，速度快（无磁盘 IO），重启后自动消失
            self.conn.register(view_name, df)

            return view_name

        except ValueError:
            raise  # ValueError 直接透传，保留友好提示
        except Exception as e:
            raise ValueError(
                f"文件 '{filename}' 解析失败。\n"
                f"请检查文件格式是否正确。\n"
                f"原始错误: {e}"
            )

    # ── 启动清理 ──────────────────────────────────────────────────────────────

    def _cleanup_uploaded_tables(self) -> None:
        """
        启动时扫描 olist.db，删除所有非 olist 原始表。

        解决问题：上次会话用 CREATE TABLE 方式写入的用户上传表，
        在服务重启后 session_state 已清空但数据库里仍残留，
        导致"当前数据表"出现无法删除的陌生表名。

        规则：表名不在 OLIST_TABLES 集合里的，全部 DROP。
        """
        try:
            rows = self.conn.execute("""
                SELECT DISTINCT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
            """).fetchdf()["table_name"].tolist()

            for t in rows:
                if t not in OLIST_TABLES:
                    self.conn.execute(f'DROP TABLE IF EXISTS "{t}"')
                    self.conn.execute(f'DROP VIEW IF EXISTS "{t}"')
        except Exception:
            pass  # 清理失败不影响启动

    # ── 视图清理 ──────────────────────────────────────────────────────────────

    def _unregister_view(self, view_name: str) -> None:
        """
        内部方法：清理指定名称的已注册视图或表，防止重复注册时出现重复条目。

        依次尝试 unregister（清理 register() 产生的虚拟表）和
        DROP VIEW（清理 CREATE VIEW 产生的视图），两者都静默忽略失败。
        """
        try:
            self.conn.unregister(view_name)
        except Exception:
            pass
        try:
            self.conn.execute(f'DROP VIEW IF EXISTS "{view_name}"')
        except Exception:
            pass

    def unload_view(self, view_name: str) -> None:
        """
        公开方法：卸载上传文件在 DuckDB 中的注册，使其不再可查询。

        与 load_uploaded_file 对应：用 register() 注册的用 unregister() 移除，
        纯内存操作，无磁盘 IO，立即生效。

        Parameters
        ----------
        view_name : str
            load_uploaded_file() 返回的表名。
        """
        self._unregister_view(view_name)

    # ── 增强 Schema（含表关系）────────────────────────────────────────────────

    def get_schema_with_relationships(self) -> str:
        """
        返回带表关系注释的 schema 文本，专为 NL2SQL prompt 设计。

        在 get_schema() 基础上，在开头附加 OLIST_RELATIONSHIPS 中定义的
        表关系说明（SQL 注释格式），帮助 LLM 在涉及多表时选择正确的 JOIN 键。

        对于用户上传的自定义表，只追加基础 schema，不附加关系注释。
        """
        rel_text = "\n".join(OLIST_RELATIONSHIPS)
        schema   = self.get_schema()
        return f"【表关系说明】\n{rel_text}\n\n【表结构详情】\n{schema}"

    def estimate_row_count(self, sql: str) -> int:
        """
        预估 SQL 查询的返回行数，用于在确认卡片中提示用户数据量级。

        实现方式：将原 SQL 包裹在 COUNT(*) 子查询中执行。
        对于大表 / 复杂 JOIN，此操作本身可能耗时，调用方应在 spinner 内调用。

        Returns
        -------
        int
            预估行数。执行失败时返回 -1（调用方应将 -1 显示为"估算失败"）。
        """
        try:
            count_sql = f"SELECT COUNT(*) AS _cnt FROM ({sql}) AS _subq"
            result    = self.conn.execute(count_sql).fetchone()
            return int(result[0]) if result else 0
        except Exception:
            return -1

    # ── 资源释放 ──────────────────────────────────────────────────────────────

    def close(self) -> None:
        """
        关闭数据库连接，释放文件锁。

        Streamlit App 通常不需要手动调用（进程结束时自动释放），
        但在测试或脚本场景下建议显式调用。
        """
        try:
            self.conn.close()
        except Exception:
            pass  # 关闭失败静默处理，不影响业务逻辑
