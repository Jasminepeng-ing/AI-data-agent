"""
scripts/init_db.py
==================
初始化脚本：把 data/raw/ 下的 9 个 Olist CSV 文件加载到 DuckDB 数据库。

使用方式（在项目根目录 AI-data-agent/ 下运行）：
    python scripts/init_db.py

执行效果：
    - 生成 / 覆盖 data/olist.db
    - 打印每张表的行数和字段数，方便快速验证数据是否完整
"""

import os
import sys
import duckdb

# Windows 控制台默认 GBK 编码，强制改为 UTF-8，避免 ✓ ✗ 等符号报错
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ── 路径常量 ──────────────────────────────────────────────────────────────────
# 以本脚本所在目录为起点，向上一级找到项目根目录
# 这样无论在哪个工作目录执行脚本，路径都不会出错
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw")     # CSV 原始文件目录
DB_PATH  = os.path.join(PROJECT_ROOT, "data", "olist.db")  # 目标 DuckDB 文件


def clean_table_name(filename: str) -> str:
    """
    将 CSV 文件名转换为简洁的表名。

    转换规则：
        1. 去掉 .csv 后缀
        2. 去掉 olist_ 前缀（如果有）
        3. 去掉 _dataset 后缀（如果有）

    示例：
        olist_orders_dataset.csv              → orders
        olist_order_items_dataset.csv         → order_items
        product_category_name_translation.csv → product_category_name_translation

    Parameters
    ----------
    filename : str
        CSV 文件名（仅文件名，不含路径）

    Returns
    -------
    str
        清洗后的表名
    """
    name = filename.replace(".csv", "")   # 去后缀

    if name.startswith("olist_"):
        name = name[len("olist_"):]       # 去 olist_ 前缀

    if name.endswith("_dataset"):
        name = name[: -len("_dataset")]   # 去 _dataset 后缀

    return name


def init_database() -> None:
    """
    主流程：扫描 CSV 文件 → 删旧建新 DB → 逐表加载 → 打印统计。

    Returns
    -------
    None
        直接打印结果到控制台；出错时打印错误信息并以 exit(1) 退出。
    """

    # ── 1. 收集所有 CSV 文件 ─────────────────────────────────────────────────
    if not os.path.exists(DATA_DIR):
        print(f"[错误] 找不到数据目录: {DATA_DIR}")
        print("请先把 CSV 文件放到 data/raw/ 目录下。")
        sys.exit(1)

    csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]

    if not csv_files:
        print(f"[错误] {DATA_DIR} 下没有找到任何 .csv 文件。")
        sys.exit(1)

    print(f"发现 {len(csv_files)} 个 CSV 文件，准备写入数据库...\n")

    # ── 2. 如果 olist.db 已存在，先删除 ──────────────────────────────────────
    # 保证脚本可以幂等重跑，不会因为旧表结构残留导致奇怪错误
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"[清理] 已删除旧数据库: {DB_PATH}")

    # ── 3. 连接（此时会自动创建新文件）──────────────────────────────────────
    try:
        conn = duckdb.connect(DB_PATH)
        print(f"[创建] 新数据库: {DB_PATH}\n")
    except Exception as e:
        print(f"[错误] 无法创建数据库: {e}")
        sys.exit(1)

    # ── 4. 逐个 CSV 加载为表 ─────────────────────────────────────────────────
    success_count = 0

    for filename in sorted(csv_files):
        table_name = clean_table_name(filename)
        # Windows 路径里的反斜杠会让 DuckDB SQL 解析出错，统一换成正斜杠
        csv_path = os.path.join(DATA_DIR, filename).replace("\\", "/")

        try:
            # read_csv_auto：DuckDB 内置函数，自动推断列类型
            conn.execute(f"""
                CREATE TABLE "{table_name}" AS
                SELECT * FROM read_csv_auto('{csv_path}', header=true)
            """)

            # 查询行数，用于验证加载是否完整
            row_count = conn.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]

            # 查询字段数
            col_count = conn.execute(f"""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
            """).fetchone()[0]

            print(f"  ✓ {table_name:<48} {row_count:>8} 行  {col_count:>3} 列")
            success_count += 1

        except Exception as e:
            # 某个文件出错不中断整体流程，打印后继续
            print(f"  ✗ {filename} 加载失败: {e}")

    # ── 5. 打印汇总 ───────────────────────────────────────────────────────────
    print(f"\n{'─' * 62}")
    print(f"初始化完成！成功加载 {success_count} / {len(csv_files)} 张表")
    print(f"数据库路径: {DB_PATH}")
    print(f"{'─' * 62}")

    conn.close()


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_database()
