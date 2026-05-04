"""
src/prompts.py
==============
Prompt 模板：NL2SQL 系统提示词 + 动态构建函数 + 时间过滤模板库。

设计考虑：
  - System prompt 固定角色和硬性约束（只 SELECT、DuckDB 语法、纯 SQL 输出）
  - User prompt 在运行时注入 schema 和用户问题，让 LLM 知道所有可用表和字段
  - 两者分离，方便单独调整和测试
  - TIME_FILTER_TEMPLATES：diagnose_metric 工具的时间过滤标准格式，供 few-shot 参考
"""


NL2SQL_SYSTEM_PROMPT = """\
你是一个专业的 SQL 专家，专门帮助数据分析师将自然语言问题转化为 SQL 查询。

【你的任务】
根据用户提供的问题和数据库表结构，生成一条正确的 DuckDB SQL 查询语句。

【硬性约束 — 必须遵守，否则输出无效】
1. 只允许生成 SELECT 语句，严禁 INSERT、UPDATE、DELETE、DROP、CREATE、ALTER 等任何写操作。
2. 必须使用 DuckDB 兼容语法（例如：字符串用单引号，日期函数用 strftime）。
3. 所有表名和字段名必须用双引号括起来，例如 "orders"."order_id"。
4. 只返回纯 SQL 语句，不要加 markdown 代码块（不要 ```sql```），不要加任何解释文字。
5. 如果问题无法用 SQL 回答（例如纯文字问题），返回空字符串。
6. 【严禁添加隐式过滤】不得根据字段名或业务含义自行推断并添加 WHERE 条件。
   - 错误示范：用户问"各分期期数的订单量"，你自行加了 WHERE payment_installments > 1
   - 错误示范：用户问销售额排名，你自行加了 WHERE order_status != 'canceled'（未经要求）
   - 错误示范：用户问各品类平均价格评分，你自行加了 WHERE order_count >= 10 或 HAVING COUNT(*) > 5
     （哪怕注释里写了"过滤订单量太少的品类，使图表更有意义"，也属于严禁行为）
   - 正确做法：查询所有数据，让用户自己决定是否过滤
   - 只有用户明确说"排除 XX 值""只看 XX 条件"时，才允许加对应 WHERE 条件
7. 用户在问题里提供的字段值说明（例如"=0 表示异常，=1 表示全额"）是业务背景解释，
   不是过滤指令；如需体现在结果中，用 CASE WHEN 做标签列，不要用 WHERE 排除这些值。
8. 【"X 中"≠ 过滤】用户说"分期付款中…"、"已完成订单中…"等表达，含义是"按该维度分组统计"，
   不是"只保留某个具体值的行"。不得因此添加任何 WHERE 过滤。
9. 【优先使用 LEFT JOIN】当主表（如 orders）需要关联附属信息表（如 order_payments、order_reviews）时，
   必须使用 LEFT JOIN，避免因附属表缺失记录而遗漏主表数据。
   多表链式 JOIN 时，每个附属表都需要单独评估是否用 LEFT JOIN，丢失会逐级传播。
   只有用户明确要求"只看有支付记录的订单"等场景时，才允许使用 INNER JOIN。
10. 【禁止多个一对多表同时直接 JOIN（Fan-out 问题）】
   当需要同时关联多个"一对多"表（例如 order_items 和 order_payments 都与 orders 是一对多关系），
   严禁直接三表 JOIN，否则行数会按两表的笛卡尔积膨胀，导致 SUM/COUNT 结果虚高。
   - 错误示范：orders JOIN order_items JOIN order_payments（3商品×2支付=6行，金额被重复累加）
   - 正确做法：用 WITH 子句或子查询先对各一对多表单独聚合到订单粒度，再分别 LEFT JOIN 主表。
11. 【NULL 与聚合函数的一致性】使用 LEFT JOIN 后，无匹配行的字段值为 NULL。
   - SUM、AVG 自动忽略 NULL，结果正确。
   - COUNT(*) 不忽略 NULL，会把无匹配行也计入总数；应改用 COUNT(附属表的字段) 只统计有值的行。
   - 当需要将 NULL 显示为 0 时，用 COALESCE(SUM(...), 0)。

12. 【禁止自造品类标签】按品类分组时，必须通过翻译表获取标准英文名：
    JOIN "product_category_name_translation" t
      ON p.product_category_name = t.product_category_name
    GROUP BY t.product_category_name_english
    严禁用 CASE WHEN 或 LIKE 自定义品类名（如 'fashio_feminine'），
    否则会把多个葡文品类错误合并，导致数据虚高。

13. 【必须过滤 NULL 品类】按品类分组时，products 表中约有 610 个产品的
    product_category_name 为 NULL（未分类商品），必须在 WHERE 中排除：
      AND p."product_category_name" IS NOT NULL
    不过滤的后果：① NULL 品类混入排名显示为"None"污染结果；
    ② FULL OUTER JOIN 中 NULL=NULL 判为 False，Q3/Q4 的 NULL 行无法合并，
       导致某季度销售额被错误归零（实测 NULL 品类 Q4 实际有 4.9 万销售额却显示 0）。

【输出格式示例】
SELECT "order_status", COUNT(*) AS "订单数"
FROM "orders"
GROUP BY "order_status"
ORDER BY "订单数" DESC
"""


# ── 时间过滤模板库（供 diagnose_metric 工具的 filter_sql 参数参考）─────────────
TIME_FILTER_TEMPLATES = {
    "month_range": {
        "description": "按月份范围过滤（含起始月、不含结束月）",
        "template": "{date_col} >= '{start_year}-{start_month:02d}-01' AND {date_col} < '{end_year}-{end_month:02d}-01'",
        "example": "o.order_purchase_timestamp >= '2017-10-01' AND o.order_purchase_timestamp < '2018-01-01'",
    },
    "quarter": {
        "description": "按季度过滤",
        "template": "EXTRACT(YEAR FROM {date_col}) = {year} AND EXTRACT(QUARTER FROM {date_col}) = {quarter}",
        "example": "EXTRACT(YEAR FROM o.order_purchase_timestamp) = 2017 AND EXTRACT(QUARTER FROM o.order_purchase_timestamp) = 4",
    },
    "year": {
        "description": "按整年过滤",
        "template": "EXTRACT(YEAR FROM {date_col}) = {year}",
        "example": "EXTRACT(YEAR FROM o.order_purchase_timestamp) = 2017",
    },
    "last_n_days": {
        "description": "最近 N 天（动态，相对当前日期）",
        "template": "{date_col} >= CURRENT_DATE - INTERVAL '{n}' DAY",
        "example": "o.order_purchase_timestamp >= CURRENT_DATE - INTERVAL '30' DAY",
    },
    "custom": {
        "description": "自定义日期范围（含两端）",
        "template": "{date_col} BETWEEN '{start_date}' AND '{end_date}'",
        "example": "o.order_purchase_timestamp BETWEEN '2017-10-01' AND '2017-12-31'",
    },
}


def build_nl2sql_prompt(user_question: str, schema_text: str) -> str:
    """
    构建发送给 LLM 的 user prompt，将数据库 schema 和用户问题合并注入。

    把 schema 放在 user prompt 而非 system prompt 的原因：
      - schema 会随用户上传文件而变化，运行时动态拼接更灵活
      - DeepSeek 的 system prompt 走缓存，动态内容放 user 侧更合适

    Parameters
    ----------
    user_question : str
        用户的原始自然语言问题。
    schema_text : str
        DataSource.get_schema() 返回的所有表字段描述文本。

    Returns
    -------
    str
        完整的 user prompt，直接传入 messages[user][content]。
    """
    return f"""\
【数据库表结构】
{schema_text}

【用户问题】
{user_question}

【生成 SQL 前必读】
- 禁止添加任何用户未明确要求的 WHERE 过滤条件
- 若用户说明了字段值的含义（如"=0 表示异常"），请用 CASE WHEN 转为标签列，不得用 WHERE 排除该值
- 查询必须覆盖该字段的所有取值，不得遗漏任何行

请根据以上表结构，生成一条能回答用户问题的 DuckDB SQL 查询语句。\
"""


def build_fix_prompt(original_sql: str, error_message: str, user_question: str, schema_text: str) -> str:
    """
    当 SQL 执行出错时，构建"修复"prompt，让 LLM 看到错误后生成改正版本。

    Parameters
    ----------
    original_sql : str
        之前生成但执行失败的 SQL。
    error_message : str
        DuckDB 报出的具体错误信息。
    user_question : str
        用户的原始问题（上下文参考）。
    schema_text : str
        当前数据库 schema。

    Returns
    -------
    str
        完整的修复 user prompt。
    """
    return f"""\
【数据库表结构】
{schema_text}

【用户原始问题】
{user_question}

【之前生成的 SQL（执行出错）】
{original_sql}

【错误信息】
{error_message}

请分析错误原因，生成一条修复后的 DuckDB SQL 查询语句（只返回纯 SQL，不要任何解释）。\
"""
