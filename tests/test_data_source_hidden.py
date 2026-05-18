"""
tests/test_data_source_hidden.py
=================================
验证 DataSource 会话级隐藏机制的三个核心行为：
  (a) 不传 hidden_tables -> 返回全部表
  (b) 传入 hidden_tables={'orders'} -> orders 不出现在结果中
  (c) 对隐藏表执行 SQL -> 触发 ValueError

注意：使用内存 DuckDB（":memory:"）避免与 Streamlit 进程争抢 olist.db 文件锁。
"""

import sys
import os
import pytest
import duckdb
import pandas as pd
from unittest.mock import patch

# 确保 src/ 在 import 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from data_source import DataSource, OLIST_BUILTIN_TABLES


@pytest.fixture(scope="module")
def ds():
    """使用内存数据库，创建模拟 Olist 表结构供测试。"""
    source = DataSource.__new__(DataSource)
    source.db_path = ":memory:"
    source.conn = duckdb.connect(":memory:")

    # 创建模拟 Olist 表（结构即可，不需要真实数据）
    source.conn.execute("""
        CREATE TABLE orders (
            order_id VARCHAR,
            customer_id VARCHAR,
            order_status VARCHAR
        )
    """)
    source.conn.execute("""
        CREATE TABLE customers (
            customer_id VARCHAR,
            customer_city VARCHAR
        )
    """)
    source.conn.execute("""
        CREATE TABLE order_items (
            order_id VARCHAR,
            product_id VARCHAR,
            price DOUBLE
        )
    """)
    # 插入少量测试数据
    source.conn.execute("INSERT INTO orders VALUES ('o1','c1','delivered')")
    source.conn.execute("INSERT INTO customers VALUES ('c1','São Paulo')")
    source.conn.execute("INSERT INTO order_items VALUES ('o1','p1',99.9)")

    yield source
    source.close()


# ── (a) 不传 hidden_tables，返回全部表 ──────────────────────────────────────

def test_list_tables_no_hidden(ds):
    tables = ds.list_tables()
    print(f"\n[a] 全部表: {tables}")
    assert "orders" in tables
    assert "customers" in tables
    assert "order_items" in tables
    assert len(tables) == 3


def test_get_schema_no_hidden(ds):
    schema = ds.get_schema()
    print(f"\n[a] schema:\n{schema}")
    assert "orders" in schema
    assert "customers" in schema
    assert "order_items" in schema


def test_get_table_info_no_hidden(ds):
    infos = ds.get_table_info()
    names = [i["name"] for i in infos]
    print(f"\n[a] get_table_info: {names}")
    assert "orders" in names
    assert "customers" in names
    # 验证结构字段
    for info in infos:
        assert "name" in info
        assert "type" in info
        assert info["type"] in ("builtin", "uploaded")
        assert "row_count" in info and isinstance(info["row_count"], int)
        assert "col_count" in info and isinstance(info["col_count"], int)
        assert "columns" in info and isinstance(info["columns"], list)


# ── (b) 传入 hidden_tables={'orders'}，orders 不出现在结果中 ─────────────────

def test_list_tables_with_hidden(ds):
    tables = ds.list_tables(hidden_tables={"orders"})
    print(f"\n[b] 隐藏 orders 后的表列表: {tables}")
    assert "orders" not in tables, "orders 应被过滤"
    assert "customers" in tables, "其他表不受影响"
    assert "order_items" in tables


def test_get_schema_with_hidden(ds):
    schema = ds.get_schema(hidden_tables={"orders"})
    print(f"\n[b] 隐藏 orders 后 schema:\n{schema}")
    lines = schema.split("\n")
    table_names_in_schema = [
        l.replace("表名: ", "").strip()
        for l in lines if l.startswith("表名: ")
    ]
    assert "orders" not in table_names_in_schema, "orders 不应出现在 schema 中"
    assert "customers" in table_names_in_schema


def test_get_table_info_with_hidden(ds):
    infos = ds.get_table_info(hidden_tables={"orders"})
    names = [i["name"] for i in infos]
    print(f"\n[b] get_table_info 隐藏 orders 后: {names}")
    assert "orders" not in names
    assert "customers" in names


def test_olist_builtin_tables_constant():
    """OLIST_BUILTIN_TABLES 应包含 9 张 Olist 表。"""
    assert isinstance(OLIST_BUILTIN_TABLES, set)
    assert len(OLIST_BUILTIN_TABLES) == 9
    assert "orders" in OLIST_BUILTIN_TABLES
    assert "customers" in OLIST_BUILTIN_TABLES
    print(f"\n[b] OLIST_BUILTIN_TABLES: {OLIST_BUILTIN_TABLES}")


# ── (c) 对隐藏表执行 SQL -> 触发 ValueError ──────────────────────────────────

def test_query_hidden_table_raises(ds):
    with pytest.raises(ValueError) as exc_info:
        ds.query("SELECT COUNT(*) FROM orders", hidden_tables={"orders"})
    error_msg = str(exc_info.value)
    print(f"\n[c] 错误信息: {error_msg}")
    assert "orders" in error_msg, "错误信息应包含表名"
    assert "隐藏" in error_msg or "刷新" in error_msg, "错误信息应提示用户操作"


def test_query_normal_table_works(ds):
    # 只隐藏 orders，查询 customers 应正常
    df = ds.query("SELECT COUNT(*) AS cnt FROM customers", hidden_tables={"orders"})
    assert not df.empty
    assert df["cnt"].iloc[0] >= 0
    print(f"\n[c] customers 查询正常，行数: {df['cnt'].iloc[0]}")


def test_query_sql_with_hidden_in_subquery(ds):
    # 子查询中引用隐藏表也应被检测到
    sql = "SELECT * FROM (SELECT order_id FROM orders LIMIT 5) t"
    with pytest.raises(ValueError) as exc_info:
        ds.query(sql, hidden_tables={"orders"})
    print(f"\n[c] 子查询隐藏表检测: {str(exc_info.value)[:100]}")
    assert "orders" in str(exc_info.value)
