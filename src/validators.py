"""
src/validators.py
=================
校验逻辑：图表类型自动校验/降级 + diagnose_metric 参数安全检查。

- validate_chart_type      : make_chart 调用前校验，不合适的图表类型自动降级
- validate_diagnose_params : diagnose_metric 调用前校验，防止 SQL 注入和空参数
"""

import re

import pandas as pd


def validate_chart_type(
    chart_type: str,
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    y_cols: list | None = None,
) -> tuple[str, str | None]:
    """
    对 LLM 选择的图表类型做常识性校验，不合适时自动降级并返回警告信息。

    Parameters
    ----------
    chart_type : str
        LLM 请求的图表类型（如 "pie"、"line"）。
    df : pd.DataFrame
        待绘图数据，用于检查列类型和类别数量。
    x_col : str
        X 轴字段名。
    y_col : str
        Y 轴字段名。

    Returns
    -------
    tuple[str, str | None]
        (最终使用的 chart_type, 警告信息或 None)
        - 若发生类型切换，返回新类型 + 说明原因的警告文字
        - 若仅有轻微问题（只警告不切换），返回原类型 + 警告文字
        - 若一切正常，返回原类型 + None
    """

    # ── 规则 1：饼图 / 环形图类别数限制 ────────────────────────────────────────
    # 超过 12 个类别的饼图严重失真，自动切换为横向条形图（视觉效果更好）
    if chart_type in ("pie", "donut") and x_col in df.columns:
        n_unique = df[x_col].nunique()
        if n_unique > 12:
            return (
                "barh",
                f"类别数（{n_unique} 个）超过 12 个，饼图会严重失真，已自动切换为横向条形图",
            )

    # ── 规则 2：折线图 X 轴必须能解析为时间格式 ─────────────────────────────────
    # 用分类字段（如省份、品类）画折线图没有意义，自动切换为柱状图
    if chart_type == "line" and x_col in df.columns:
        try:
            pd.to_datetime(df[x_col])
        except Exception:
            return (
                "bar",
                f"X 轴字段 '{x_col}' 无法解析为时间格式，折线图仅适用于时间序列，已自动切换为柱状图",
            )

    # ── 规则 3：散点图要求 X、Y 轴均为数值类型 ──────────────────────────────────
    if chart_type == "scatter":
        if x_col in df.columns and not pd.api.types.is_numeric_dtype(df[x_col]):
            return (
                "bar",
                f"散点图要求 X 轴为数值类型，'{x_col}' 是文本列，已自动切换为柱状图",
            )
        if y_col in df.columns and not pd.api.types.is_numeric_dtype(df[y_col]):
            return (
                "bar",
                f"散点图要求 Y 轴为数值类型，'{y_col}' 是文本列，已自动切换为柱状图",
            )

    # ── 规则 4：数据量过少（仅警告，不切换）────────────────────────────────────
    if len(df) == 1:
        return chart_type, "数据只有 1 行，图表意义有限，建议直接阅读数值"

    # ── 规则 5：气泡图校验 ───────────────────────────────────────────────────────
    if chart_type == "bubble":
        if x_col in df.columns and not pd.api.types.is_numeric_dtype(df[x_col]):
            return (
                "bar",
                f"气泡图 X 轴必须是数值字段，'{x_col}' 是文本列，已自动切换为柱状图",
            )
        if y_col in df.columns and not pd.api.types.is_numeric_dtype(df[y_col]):
            return (
                "bar",
                f"气泡图 Y 轴必须是数值字段，'{y_col}' 是文本列，已自动切换为柱状图",
            )
        if len(df) < 3:
            return (
                "table",
                f"气泡图数据量过少（< 3 条），已使用表格展示",
            )
        if len(df) > 200:
            return (
                chart_type,
                f"数据量较大（{len(df)} 条），气泡可能重叠，建议增加过滤条件",
            )

    # ── 规则 6：多系列（y_cols）校验 ────────────────────────────────────────────
    if y_cols is not None and len(y_cols) > 0:
        if len(y_cols) > 15:
            return (
                chart_type,
                f"系列数量（{len(y_cols)} 个）过多，图表可能难以阅读，建议不超过 6 个系列",
            )
        if chart_type in ("pie", "donut"):
            return (
                "bar",
                "饼图不支持多系列，已自动切换为分组柱状图（bar）",
            )
        if chart_type == "scatter":
            return (
                "bar",
                "散点图不支持多系列 y_cols，请使用 color_col 区分系列，已切换为 bar",
            )

    return chart_type, None


# ── wordcloud 输入校验 ────────────────────────────────────────────────────────

def validate_wordcloud_input(
    df: pd.DataFrame,
    wc_opts: dict,
) -> tuple[bool, str]:
    """
    校验词云图的输入参数完整性和数据有效性。

    Parameters
    ----------
    df      : 查询结果 DataFrame
    wc_opts : wordcloud_options 字典（来自 make_chart 的 wordcloud_options 参数）

    Returns
    -------
    (is_valid: bool, message: str)
        is_valid=True  且 message 非空 → 仅警告（可继续生成）
        is_valid=False 且 message 非空 → 错误（应终止生成）
        is_valid=True  且 message 为空 → 一切正常
    """
    text_col = wc_opts.get("text_col")
    word_col = wc_opts.get("word_col")
    freq_col = wc_opts.get("freq_col")

    # ── 1. 至少提供一组有效输入 ────────────────────────────────────────────────
    has_text_mode  = bool(text_col)
    has_word_mode  = bool(word_col and freq_col)

    if not has_text_mode and not has_word_mode:
        return (
            False,
            "参数不完整：必须提供 text_col（原始文本列），"
            "或同时提供 word_col + freq_col（词语列 + 词频列）。",
        )

    # ── 2. text_col 模式：检查列存在 & 非全空 ─────────────────────────────────
    if has_text_mode:
        if text_col not in df.columns:
            return False, f"text_col 指定的列 '{text_col}' 不存在，可用列：{list(df.columns)}"
        non_empty = df[text_col].dropna().astype(str).str.strip().str.len() > 0
        if not non_empty.any():
            return False, f"文本列 '{text_col}' 全为空值，无法生成词云。"

    # ── 3. word_col + freq_col 模式：检查列存在 & freq_col 为数值 ─────────────
    if has_word_mode:
        if word_col not in df.columns:
            return False, f"word_col 指定的列 '{word_col}' 不存在，可用列：{list(df.columns)}"
        if freq_col not in df.columns:
            return False, f"freq_col 指定的列 '{freq_col}' 不存在，可用列：{list(df.columns)}"
        if not pd.api.types.is_numeric_dtype(df[freq_col]):
            return False, f"词频列 '{freq_col}' 必须是数值类型，当前类型为 {df[freq_col].dtype}。"

    # ── 4. 有效词数过少（仅警告）──────────────────────────────────────────────
    # 粗估有效行数（不做完整分词，仅检查非空行数）
    if has_word_mode:
        valid_rows = df[word_col].dropna().astype(str).str.strip().str.len() > 0
        if valid_rows.sum() < 5:
            return True, f"有效词数过少（< 5 行），词云效果可能较差。"
    elif has_text_mode:
        valid_rows = df[text_col].dropna().astype(str).str.strip().str.len() > 0
        if valid_rows.sum() < 1:
            return True, "文本行数过少，词云效果可能较差。"

    return True, ""


# ── diagnose_metric 参数校验 ──────────────────────────────────────────────────

_DANGEROUS_KEYWORDS = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE",
    "ALTER", "TRUNCATE", "EXEC", "EXECUTE",
})


def validate_diagnose_params(
    base_sql: str,
    period_a: dict,
    period_b: dict,
    drill_dimensions: list,
) -> tuple[bool, str]:
    """
    对 diagnose_metric 的入参做安全性和完整性校验。

    Parameters
    ----------
    base_sql         : LLM 提供的基础 SQL（SELECT + FROM/JOIN，不含 WHERE）
    period_a, period_b : 各含 label / filter_sql 键的时间段字典
    drill_dimensions : 下钻维度列表，每项含 dimension_name / dimension_col

    Returns
    -------
    (is_valid: bool, error_message: str)
        is_valid=True 时 error_message 为空字符串
    """
    # ── 1. base_sql 危险关键字检查 ────────────────────────────────────────────
    for kw in _DANGEROUS_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", base_sql, re.IGNORECASE):
            return False, f"base_sql 包含危险关键字 '{kw}'，只允许 SELECT 查询"

    if "SELECT" not in base_sql.upper():
        return False, "base_sql 必须包含 SELECT 子句"

    if "FROM" not in base_sql.upper():
        return False, "base_sql 必须包含 FROM 子句"

    # ── 2. period filter_sql 非空 + 危险关键字检查 ────────────────────────────
    for period_name, period in [("period_a", period_a), ("period_b", period_b)]:
        if not period:
            return False, f"{period_name} 不能为空"
        filter_sql = (period.get("filter_sql") or "").strip()
        if not filter_sql:
            return False, f"{period_name}.filter_sql 不能为空（参考标准格式：EXTRACT(YEAR FROM ...) = 2017）"
        for kw in _DANGEROUS_KEYWORDS:
            if re.search(r"\b" + kw + r"\b", filter_sql, re.IGNORECASE):
                return False, f"{period_name}.filter_sql 包含危险关键字 '{kw}'"
        if not period.get("label", "").strip():
            return False, f"{period_name}.label 不能为空（如 '2017 Q3'）"

    # ── 3. drill_dimensions 非空 + 必要字段检查 ──────────────────────────────
    if not drill_dimensions:
        return False, "drill_dimensions 至少需要 1 个维度"

    for i, dim in enumerate(drill_dimensions):
        if not dim.get("dimension_name", "").strip():
            return False, f"drill_dimensions[{i}].dimension_name 不能为空"
        if not dim.get("dimension_col", "").strip():
            return False, f"drill_dimensions[{i}].dimension_col 不能为空（如 'p.product_category_name'）"

    return True, ""
