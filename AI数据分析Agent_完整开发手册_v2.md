# AI 数据分析 Agent · 完整开发手册 v2

> 适用对象:有 SQL + Pandas 基础,使用 Claude Code 辅助开发的数据分析师
> LLM 选型:DeepSeek-V3 (deepseek-chat)
> 预计工期:4 周(每周约 10-15 小时)

---

## 修订说明(v1 → v2)

> 本次修订修复了 v1 中 5 个结构性问题,对应章节已标注 `[修订]`。

| # | 问题 | 影响 | 修复位置 |
|---|---|---|---|
| 1 | `last_result` 跨轮污染导致图表画错数据 | 🔴 严重 Bug | 3.2 节工具设计 |
| 2 | SQL 确认按钮打断 Agent 多步流 | 🟠 体验矛盾 | 2.4 节 + 3.2 节 |
| 3 | 归因工具复杂度低估,时间和实现方案不足 | 🟠 进度风险 | 4.2 节 |
| 4 | 图表类型无硬校验,完全依赖 LLM 自律 | 🟡 质量隐患 | 4.1 节 |
| 5 | 报告只有 Markdown,无法直接发给领导/同事 | 🟡 实用性缺口 | 4.3 节 |

---

## 一、项目概览

### 1.1 项目目标

构建一个面向数据分析师工作场景的 AI Agent,能够通过自然语言完成:
- 多源数据查询(Excel / CSV / Olist 数据集 / 远程数据库)
- 自动数据可视化(含图表类型自动校验)
- 多步深度分析(包括归因诊断)
- 自动生成分析报告(Markdown + Word 导出)

### 1.2 技术栈

| 模块 | 选型 | 备注 |
|---|---|---|
| 前端 | Streamlit | 半天上手,纯 Python |
| LLM | DeepSeek-V3 (deepseek-chat) | 通过 OpenAI SDK 调用 |
| Agent 编排 | 原生 Function Calling | 不用 LangChain |
| 数据存储与查询 | DuckDB | SQL 统一访问多源 |
| 数据处理 | Pandas | 辅助 |
| 可视化 | Plotly | 交互式图表 |
| 报告导出 | python-docx | Word 格式导出(v2 新增) |
| 部署 | Streamlit Community Cloud | 免费 |

### 1.3 环境准备

```bash
pip install streamlit duckdb pandas plotly openai python-dotenv openpyxl python-docx
```

`.env` 文件:
```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

### 1.4 项目目录结构

```
ai-data-agent/
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── data/
│   ├── olist.db
│   └── raw/
├── src/
│   ├── app.py               # Streamlit 主程序
│   ├── agent.py             # Agent 核心:LLM 调用 + 工具循环
│   ├── tools.py             # 工具定义(SQL/图表/分析/归因/报告)
│   ├── data_source.py       # 数据源抽象层
│   ├── prompts.py           # System Prompt 模板
│   ├── validators.py        # [v2 新增] 图表校验 + 输出质量规则
│   └── config.py
├── scripts/
│   └── init_db.py
└── docs/
    └── architecture.png
```

### 1.5 4 周路线图

| 周次 | 目标 | 交付物 |
|---|---|---|
| Week 1 | 跑通 NL2SQL 最短链路 | 能用自然语言查数据 + 显示结果 |
| Week 2 | 升级为真正的 Agent | 工具调用 + 多步规划 + 多轮记忆 + 智能确认机制 |
| Week 3 | 加深度能力 | 图表校验 + 归因诊断 + 主动洞察 + Word 导出 |
| Week 4 | 求职作品包装 | 部署 + 视频 + 文章 + 简历 |

---

## 二、Week 1 · 项目骨架搭建

### 2.1 Day 1-2:数据准备

**任务:**
1. 从 Kaggle 下载 Olist 数据集到 `data/raw/`
2. 用 Pandas 加载所有 CSV,熟悉每张表的字段和业务含义
3. 写下 10 个想让 Agent 回答的业务问题(从简单到复杂)

**10 个推荐业务问题(基于 Olist 数据集):**

| # | 问题 | 难度 | 涉及能力 |
|---|---|---|---|
| 1 | 2017 年总订单数和总销售额是多少? | ⭐ | 单表聚合 |
| 2 | 各个州(state)的订单数排名 Top 10 | ⭐ | 单表分组 + 排序 |
| 3 | 各支付方式(payment_type)的占比 | ⭐⭐ | 占比计算 + 饼图 |
| 4 | 2017 年每月销售额的趋势 | ⭐⭐ | 时间聚合 + 折线图 |
| 5 | 各品类(product_category)的平均评分 Top 10 | ⭐⭐ | 多表 JOIN |
| 6 | 平均配送时长最长的 5 个州 | ⭐⭐ | 时间差计算 + 多表 JOIN |
| 7 | 2017 年 Q4 vs Q3 各品类销售额对比 | ⭐⭐⭐ | 时间分段 + 对比 |
| 8 | 高客单价用户(Top 20%)的特征画像 | ⭐⭐⭐ | 用户分层 + 聚合 |
| 9 | 为什么 2018 年某月销售额突然下降? | ⭐⭐⭐⭐ | **归因分析** |
| 10 | 基于历史数据,预测下个月各品类销售趋势 | ⭐⭐⭐⭐ | 时间序列 + 预测 |

### 2.2 Day 3-4:Streamlit 骨架 + 数据库初始化

**📋 Prompt 模板(发给 Claude Code):**

```
我在做一个数据分析 Agent 项目,用于求职作品集。

【项目背景】
- 技术栈: Streamlit + DuckDB + DeepSeek API + Plotly
- 数据集: Olist Brazilian E-Commerce(已下载到 ./data/raw/,9 个 CSV)
- 目录结构:
  - src/ 放代码
  - data/ 放数据
  - scripts/ 放初始化脚本

【本次任务】只做这三件事(不要扩展):

1. 写 scripts/init_db.py:
   - 把 9 个 CSV 加载到 ./data/olist.db (DuckDB 文件)
   - 表名用文件名去掉后缀和 "olist_" 前缀
     (如 olist_orders_dataset.csv → orders)
   - 加载完成后打印各表的行数和字段数
   - 如果 olist.db 已存在,先删除再重建

2. 写 src/data_source.py:
   抽象数据源模块,包含一个 DataSource 类,提供这些方法:
   - __init__(db_path): 连接 DuckDB
   - get_schema() -> str: 返回所有表的 schema 文本(给 LLM 看)
   - get_schema_with_relationships() -> str: 在 schema 基础上附加表关系注释
     例: "-- orders 通过 customer_id 关联 customers 表"
   - load_uploaded_file(file, table_name: str) -> str:
       把上传的 Excel/CSV 注册成 DuckDB 临时表,返回注册后的表名
   - query(sql) -> pandas.DataFrame: 执行 SQL 返回 DataFrame
   - estimate_row_count(sql) -> int: 估算 SQL 返回行数(用于后续确认机制)
   - list_tables() -> list[str]: 返回当前所有可查表名

3. 写 src/app.py:
   Streamlit 主程序,要有:
   - 页面标题: "AI 数据分析 Agent"
   - 左侧 sidebar:
     * 显示当前 schema(用 st.expander 折叠)
     * 文件上传组件(支持 .xlsx 和 .csv,可多文件)
     * 上传后调用 data_source.load_uploaded_file
     * 上传成功后在 sidebar 显示 "已加载: {表名}({行数}行)"
   - 主区域:
     * 聊天界面,用 st.chat_input + st.chat_message
     * 用 st.session_state 保存对话历史
     * 当前不接 LLM,用户输入先简单 echo: "你说的是: {输入}"

【约束】
- 所有代码必须有详细中文注释
- 函数都要有 docstring
- 错误要 try-catch 并显示友好提示

【交付方式】
请按这个顺序输出,每写完一个文件先解释:
1. 这个文件解决了什么问题
2. 关键设计选择和原因
3. 为后续 Week 2/3 留了哪些"接口"

写完一个文件后停一下,我跑通了再让你写下一个。
```

**✅ Week 1 Day 3-4 完成标志:**
- 能运行 `streamlit run src/app.py`
- 看到聊天界面 + sidebar
- 上传 Excel 文件能成功注册到 DuckDB
- sidebar 能看到所有表的 schema

### 2.3 Day 5-6:接通 DeepSeek 实现 NL2SQL

**📋 Prompt 模板(发给 Claude Code):**

```
基于上一步的项目,现在要加 NL2SQL 能力。

【任务】

1. 写 src/config.py:
   - 从 .env 读 DEEPSEEK_API_KEY
   - 定义常量:
     * DEEPSEEK_BASE_URL = "https://api.deepseek.com"
     * MODEL_NAME = "deepseek-chat"
     * MAX_TOKENS = 4000
     * LARGE_QUERY_ROW_THRESHOLD = 100000  # 超过此行数才弹确认

2. 写 src/prompts.py:
   - 定义 NL2SQL_SYSTEM_PROMPT:
     * 角色: "你是一个 SQL 专家"
     * 任务: 根据用户问题和数据库 schema 生成 SQL
     * 约束:
       - 只生成 SELECT,禁止 INSERT/UPDATE/DELETE/DROP
       - 必须用 DuckDB 兼容语法
       - 返回纯 SQL,不要 markdown 代码块包裹
       - 字段名要加双引号(DuckDB 习惯)
   - 提供函数 build_nl2sql_prompt(user_question, schema_text) -> str

3. 修改 src/app.py:
   - 用户输入 → 调用 DeepSeek API 生成 SQL
   - 显示 LLM 生成的 SQL(用 st.code 在 expander 里折叠)
   - 加"确认执行"按钮(Week 1 阶段所有查询都要确认,
     Week 2 升级 Agent 后会改为智能确认机制)
   - 点击后调用 data_source.query(sql),用 st.dataframe 显示结果

4. 错误处理:
   - SQL 执行报错: 显示错误信息,提示用户可以"让 AI 修复"
   - "让 AI 修复"按钮: 把错误信息和原 SQL 发给 LLM,让它生成新版本

【DeepSeek API 调用示例】
from openai import OpenAI

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_question}
    ],
    max_tokens=4000,
    temperature=0.1   # SQL 生成需要确定性
)
sql = response.choices[0].message.content

【交付方式】
- 写完后告诉我: 你的 Prompt 工程做了哪些考虑?
- 为什么 temperature 设 0.1 而不是 0.7?
- 如果用户问的问题需要 JOIN 多张表,你怎么让 LLM 知道?
```

**✅ Week 1 Day 5-6 完成标志:**
- 用户输入"2017 年总订单数是多少"
- 屏幕显示生成的 SQL
- 点击确认后,显示结果
- SQL 报错能用"让 AI 修复"自动修正

### 2.4 Day 7:Schema 优化 + 确认机制预设计 [修订]

> ⚠️ **v2 修订说明(对应问题 2)**
>
> v1 在这里设计了"所有查询都需要点确认"的流程。但这个机制在 Week 2
> 升级成 Agent 后会产生严重的体验矛盾——Agent 自主多步执行时,
> 每一步都弹确认框会把连贯的分析过程切得支离破碎。
>
> **本节的修改:**
> - Day 7 仍然实现确认机制,但同时预埋"智能确认"的接口
> - Week 2 Day 10-11 会把确认逻辑改成:只有预估行数 > 10万 的查询才弹确认
> - 普通查询改为直接执行 + 提供"撤销上一步"按钮

**📋 Prompt 模板:**

```
现在要让 NL2SQL 更可靠,同时为 Week 2 的 Agent 升级预埋正确的架构接口。

【任务】

1. 改进 SQL 生成:
   - 在 SYSTEM_PROMPT 里加上重要表的"关系说明"(用注释方式)
   - 例如: "-- orders 表通过 customer_id 关联 customers 表"
   - 调用 data_source.get_schema_with_relationships() 获取

2. 把"确认执行"逻辑封装成独立函数 should_confirm(sql, estimated_rows) -> bool:
   - 当前 Week 1 阶段: 总是返回 True(所有查询都要确认)
   - 这个函数在 Week 2 升级 Agent 时会改成智能判断:
     * estimated_rows > 100000 → True(需要确认)
     * 其他 → False(直接执行)
   - 封装成函数的目的就是 Week 2 只改这一处,不改其他代码

3. SQL 确认卡片改进:
   显示给用户的不只是 SQL,还要:
   - 查询意图描述(一句中文)
   - 涉及的表名列表
   - 是否包含 JOIN 操作
   - 预估返回行数(调用 data_source.estimate_row_count)

4. 历史 SQL 记录:
   - 在 sidebar 加 "最近查询" 列表(用 st.session_state 保存)
   - 点击历史项可以重新执行

【交付方式】
单独输出每个改动,用 diff 风格说明改了哪里。
特别说明 should_confirm 函数在 Week 2 怎么改。
```

**✅ Week 1 完成标志:**
有一个能用中文问问题、自动出 SQL、显示意图、可以确认执行、能看到历史的 NL2SQL 工具。
这时候它还不算 Agent,但已经能 demo 了。

---

## 三、Week 2 · 升级为 Agent (Function Calling)

### 3.1 Day 8-9:理解 DeepSeek Function Calling

**📋 Prompt 模板(让 Claude Code 教你):**

```
我已经做完了基础的 NL2SQL 工具。现在要把它升级成一个真正的 Agent,
核心是引入 DeepSeek 的 Function Calling 能力。

请先不要写代码,先解释清楚以下问题(用我能听懂的话,可以打比方):

1. DeepSeek 的 Function Calling 和普通 API 调用有什么区别?
2. 一个完整的 Agent 循环长什么样?(请画一个文字流程图)
3. tools 参数怎么定义?给我一个最简单的例子(比如定义一个 add(a, b) 工具)
4. LLM 返回 tool_calls 后,我的代码要做什么?把结果传回 LLM 时怎么传?
5. 如果 LLM 一次决定调多个工具(parallel tool calls),怎么处理?
6. DeepSeek Function Calling 有哪些常见坑?(比如假调用、JSON 不合法等)

回答完后,我们再开始改代码。
```

### 3.2 Day 10-11:重构成 Agent 架构 [修订]

> ⚠️ **v2 修订说明(对应问题 1 和问题 2)**
>
> **问题 1 修复:last_result 跨轮污染**
>
> v1 中所有工具通过 `st.session_state['last_result']` 共享数据,
> 存在严重的跨轮污染风险:
> - 用户先问 A(查了订单数据)
> - 再问 B(查了用户数据)
> - 再说"给 A 画个图"
> - 此时 `last_result` 已经是 B 的数据,图表会画错
>
> **修复方案:** 每次 `query_database` 执行时,把结果存入带意图标签的字典:
> ```python
> # 不再用单一的 last_result
> # 改为带标签的字典
> st.session_state['query_results'][intent_label] = {
>     'df': result_df,
>     'sql': sql,
>     'timestamp': datetime.now(),
>     'row_count': len(result_df)
> }
> st.session_state['latest_query_key'] = intent_label
> ```
> `make_chart` 调用时优先使用 `latest_query_key`,
> 用户可以通过 `result_key` 参数显式指定用哪次查询的数据。
>
> **问题 2 修复:确认机制改为智能确认**
>
> 把 Day 7 预埋的 `should_confirm()` 函数改成智能判断逻辑(见下方 Prompt)。

**📋 Prompt 模板:**

```
现在开始重构。目标是把当前的 NL2SQL 升级成一个真正的 Agent。

【架构调整】

1. 新建 src/tools.py,定义这 3 个工具(Week 2 先做这 3 个):

   工具 1: query_database
   参数:
   - sql: str — 要执行的 SELECT 语句
   - intent: str — 用一句中文说明这个查询的意图(如"查 2017 年各品类销售额")
   
   实现要求:
   - 执行 SQL,把结果存入 session_state['query_results'][intent] 字典:
     {
       'df': result_df,
       'sql': sql,
       'intent': intent,
       'timestamp': datetime.now().isoformat(),
       'row_count': len(result_df),
       'columns': list(result_df.columns)
     }
   - 同时更新 session_state['latest_query_key'] = intent
   - 返回给 LLM 的是文字摘要(不是完整 DataFrame):
     "查询完成: {intent}\n行数: {N}\n列: {col1, col2, ...}\n前3行预览:\n{df.head(3).to_string()}"
   - 不要返回完整数据(会占用大量 token)

   工具 2: make_chart
   参数:
   - chart_type: str — 图表类型
   - x_col: str — X 轴字段名
   - y_col: str — Y 轴字段名
   - title: str — 图表标题
   - result_key: str (可选) — 指定用哪次查询的数据,默认用 latest_query_key
   
   实现要求:
   ⚠️ 关键:画图前必须验证数据来源是否匹配
   
   def make_chart(chart_type, x_col, y_col, title, result_key=None):
       # 确定要用哪次查询的数据
       key = result_key or st.session_state.get('latest_query_key')
       if not key or key not in st.session_state.get('query_results', {}):
           return "错误: 没有可用的查询结果,请先调用 query_database"
       
       data_info = st.session_state['query_results'][key]
       df = data_info['df']
       
       # 验证字段是否存在
       if x_col not in df.columns:
           return f"错误: 字段 '{x_col}' 不存在,可用字段: {list(df.columns)}"
       if y_col not in df.columns:
           return f"错误: 字段 '{y_col}' 不存在,可用字段: {list(df.columns)}"
       
       # 调用 validators.py 做图表类型自动校验(Week 3 实现,Week 2 先留空)
       # chart_type, warning = validate_chart_type(chart_type, df, x_col, y_col)
       
       # 画图...

   工具 3: analyze_dataframe
   - 功能: 对指定查询结果做基础统计分析
   - 参数: analysis_type ("describe" | "correlation" | "groupby_summary"),
            result_key (可选,默认用 latest_query_key)
   - 返回分析结果的文字描述

2. 重写 src/agent.py,实现 Agent 主循环:

   def run_agent(user_message: str, history: list) -> str:
       """
       Agent 主循环:
       1. 构造 messages(system + history + user_message)
       2. 调 LLM,带上 tools 参数
       3. 如果 LLM 返回 tool_calls:
          a. 解析工具名和参数
          b. [智能确认] 如果是 query_database 且预估行数 > 10万,
             暂停并提示用户确认,不直接执行
          c. 其他情况直接执行工具
          d. 把结果作为 tool message 加到 messages
          e. 继续循环
       4. 如果 LLM 返回最终回答,退出循环
       5. 最大循环次数限制: MAX_ITERATIONS = 12
       """

3. [修订] 把 Day 7 的 should_confirm() 改为智能判断:

   def should_confirm(sql: str, estimated_rows: int) -> bool:
       """
       智能确认规则:
       - 预估行数 > 100000: 需要确认(大数据量查询)
       - 其他情况: 不需要确认,直接执行
       
       Week 1 时这里是 return True(全部确认)
       Week 2 起改成下面这个逻辑
       """
       return estimated_rows > 100000

4. 修改 src/app.py:
   - 用户输入直接调 run_agent()
   - Agent 自主执行时不弹确认框(除非 should_confirm 返回 True)
   - 在 UI 展示 Agent 思考过程:
     * 每次 tool_call 显示 "🔧 正在调用工具: {tool_name} - {intent}"
     * 工具结果用 expander 折叠展示
     * 在 sidebar 维护"本轮已执行查询"列表,点击可查看/重用
   - 加"撤销上一步"按钮替代原来的全局确认
     (撤销逻辑: 删除 session_state['query_results'] 最后一条,
      重建 latest_query_key)

【DeepSeek Function Calling 示例代码】

from openai import OpenAI
import json

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

tools = [
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "执行 SQL 查询,返回结果概要。结果会存入带意图标签的缓存,供后续工具使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的 SQL 语句(只能是 SELECT)"
                    },
                    "intent": {
                        "type": "string",
                        "description": "用一句中文说明这个查询的意图,如'查2017年各品类销售额'。此标签会作为数据缓存的 key。"
                    }
                },
                "required": ["sql", "intent"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,
    tools=tools,
    tool_choice="auto",
    temperature=0.3
)

message = response.choices[0].message
if message.tool_calls:
    for tool_call in message.tool_calls:
        function_name = tool_call.function.name
        try:
            function_args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            # DeepSeek 偶尔生成非法 JSON,要容错
            function_args = {}
        result = execute_tool(function_name, function_args)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": str(result)
        })

【DeepSeek 特别注意事项】
- 假调用容错: tool_calls 字段存在但内容为 None 时,当作普通回答处理
- JSON 解析: arguments 必须 try-except,失败时返回明确错误给 LLM
- temperature: 建议 0.3-0.5,不要用 0(太死板会忘记用工具)
- tool message 的 tool_call_id 必须与 assistant message 里的对应,否则 API 报错

【交付方式】
1. 先给我看 tools.py 的工具定义框架(只写定义,不实现)
2. 我确认 Schema 没问题后再写实现
3. 然后写 agent.py 主循环
4. 最后改 app.py
每写一步,告诉我做了什么决策、为什么
```

### 3.3 Day 12-13:多步分析能力

**📋 Prompt 模板:**

```
现在让 Agent 能处理需要多步骤的复杂问题。

【目标场景】
用户问: "2017 年 Q4 哪个品类销售额下跌最严重?"

Agent 应该自动规划成:
Step 1: query_database(查 Q3 各品类销售, intent="Q3各品类销售额")
Step 2: query_database(查 Q4 各品类销售, intent="Q4各品类销售额")
Step 3: analyze_dataframe(计算环比,result_key="Q4各品类销售额")
Step 4: make_chart(画对比图,result_key="Q4各品类销售额")
Step 5: 输出结论

【任务】

1. 修改 src/prompts.py 中的 AGENT_SYSTEM_PROMPT,加入分析规划要求:
   ```
   当用户问题需要多步骤完成时,你必须:
   1. 先用一段话说明分析计划(不调用工具,只输出文本)
      格式: "分析计划: 我将分 N 步完成这个分析..."
   2. 然后逐步调用工具执行
   3. 每步执行后,简要说明这一步的发现(1-2 句)
   4. 全部完成后,综合所有发现给出最终结论
   
   调用 make_chart 前,必须先确认:
   - session_state 中存在目标数据(先查询,再画图)
   - 如果需要画"对比图",先确保两组数据都已查询完毕
   - 通过 result_key 参数明确指定画哪次查询的数据
   ```

2. 修改 src/app.py:
   - 用 st.status 组件展示多步执行进度
   - 每个 tool_call 显示步骤号和 intent 标签

【交付方式】
先改 Prompt,我用 3 个问题测试:
1. "2017年总销售额" (1步)
2. "Top 10 销售品类" (2步:查询+画图)
3. "Q4 vs Q3 各品类对比" (多步)
测试通过后再优化 UI。
```

### 3.4 Day 14:多轮记忆 + 上下文管理

**📋 Prompt 模板:**

```
最后让 Agent 真正"记得"之前的对话。

【任务】

1. 在 src/agent.py 中做 token 管理:
   - messages 总长度 > 50000 字符时,截断最早的几轮
   - 始终保留: system message + 最新 6 轮对话
   - 优先截断: 旧的 tool message(这类内容最占空间)
   - 截断时: 保留被截断轮次的 assistant 最终回答,删除中间 tool_calls 细节

2. 在 prompts.py 的 AGENT_SYSTEM_PROMPT 加:
   ```
   你能看到完整的对话历史,请充分利用:
   - "那再看看华南地区"中的"那"指上一轮的分析主题
   - 用户定义过的术语(如"活跃用户=最近30天有下单")要记住并沿用
   - 已查过的数据(session_state 中有记录)不要重复查,直接引用
   - 上一轮已经分析过的维度,推荐更深层的维度而不是重复
   ```

3. 在 sidebar 加"清空对话"按钮:
   - 清空 st.session_state 中的 messages、query_results、latest_query_key

【测试场景】
对话 1: "查一下 2017 年总销售额"
对话 2: "那分到各个州看呢?"
对话 3: "Top 5 的州具体是哪些?"

三轮对话应该上下文连贯,第 2、3 轮能理解代词指向。
```

**✅ Week 2 完成标志:**
- Agent 能自主选择调用 SQL/图表/分析工具
- make_chart 只画当前对话的数据,不会画错历史数据
- 只有预估行数 > 10万的查询才弹确认框
- 多轮对话能理解上下文(代词、引用)
- UI 上能看到 Agent 的思考和执行过程

---

## 四、Week 3 · 智能图表 + 归因诊断 + 主动洞察

### 4.1 Day 15-17:智能图表系统 [修订]

> ⚠️ **v2 修订说明(对应问题 4)**
>
> v1 中图表类型完全由 LLM 自主决定,没有任何硬校验。
> 问题在于 LLM 会犯明显的错误,比如用饼图展示 20 个品类。
>
> **修复方案:** 新增 `src/validators.py`,把常识性规则用代码硬编码,
> LLM 决策的结果必须经过校验层才能执行。这层校验不是"推翻 LLM",
> 而是"纠正 LLM 的低级失误"。

**📋 Prompt 模板:**

```
现在要把图表能力做深,同时加入自动校验机制防止 LLM 画出不合理的图表。

【任务一: 新建 src/validators.py】

实现图表类型自动校验函数:

def validate_chart_type(chart_type: str, df: pd.DataFrame,
                         x_col: str, y_col: str) -> tuple[str, str | None]:
    """
    对 LLM 选择的图表类型做常识性校验和自动降级。
    返回: (最终使用的 chart_type, 警告信息或 None)
    
    校验规则:
    规则 1 - 饼图/环形图类别限制:
      if chart_type in ("pie", "donut") and df[x_col].nunique() > 5:
          return "barh", f"类别数({df[x_col].nunique()})超过 5 个,已自动切换为横向条形图"
    
    规则 2 - 折线图时间轴检查:
      if chart_type == "line":
          try: pd.to_datetime(df[x_col])
          except: return "bar", "X 轴无法解析为时间格式,已自动切换为柱状图"
    
    规则 3 - 散点图数值类型检查:
      if chart_type == "scatter":
          if not pd.api.types.is_numeric_dtype(df[x_col]):
              return "bar", "散点图要求 X 轴为数值,已自动切换为柱状图"
          if not pd.api.types.is_numeric_dtype(df[y_col]):
              return "bar", "散点图要求 Y 轴为数值,已自动切换为柱状图"
    
    规则 4 - 数据量过少警告(不切换,只警告):
      warning = None
      if len(df) == 1:
          warning = "数据只有 1 行,图表意义有限,建议使用表格"
      
    return chart_type, warning
    """
    pass  # 请实现

在 make_chart 调用画图之前,先调用这个函数。
如果发生了类型切换,在图表下方显示:
"⚠️ 图表类型已自动调整: {警告信息}"

【任务二: 完整图表工具 Schema】

请把 src/tools.py 中的 make_chart 工具改成下面这个完整 Schema:

{
    "type": "function",
    "function": {
        "name": "make_chart",
        "description": "根据查询结果生成交互式图表。图表类型会经过自动校验,不合适的类型会被自动调整。",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["line","bar","barh","pie","donut","scatter",
                             "heatmap","area","combo","table"],
                    "description": "图表类型。选择规则:\n- line: 时间序列趋势(X轴必须是时间)\n- bar: 分类对比(类别≤8个)\n- barh: 横向条形图(类别名长 或 >8个)\n- pie/donut: 构成占比(类别≤5个,总和有意义)\n- scatter: 两个连续变量相关性(X和Y都必须是数值)\n- heatmap: 二维交叉分析\n- area: 累积量或占比变化\n- combo: 双轴图(柱+线,不同单位)\n- table: 精确数值查阅\n注意: 代码层会对不合适的类型自动降级,但请尽量选对。"
                },
                "x_col": {
                    "type": "string",
                    "description": "X 轴字段名(必须是查询结果的列名)"
                },
                "y_col": {
                    "type": "string",
                    "description": "Y 轴字段名"
                },
                "y_col_2": {
                    "type": "string",
                    "description": "复合图(combo)的第二个Y轴字段,其他类型不填"
                },
                "color_col": {
                    "type": "string",
                    "description": "多系列着色的分类字段,可选"
                },
                "title": {
                    "type": "string",
                    "description": "图表标题(中文,必须包含时间维度,如'2017年各品类月度销售额')"
                },
                "x_axis_label": {
                    "type": "string",
                    "description": "X 轴标题(带单位)"
                },
                "y_axis_label": {
                    "type": "string",
                    "description": "Y 轴标题(带单位,如'销售额(元)')"
                },
                "result_key": {
                    "type": "string",
                    "description": "指定用哪次查询的数据(对应 query_database 的 intent 参数)。不填则用最近一次查询。跨轮对话时必须明确填写。"
                },
                "format_options": {
                    "type": "object",
                    "properties": {
                        "sort_by": {
                            "type": "string",
                            "enum": ["x_asc","x_desc","y_asc","y_desc","none"],
                            "description": "排序方式,Top N 场景用 y_desc"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "只显示前 N 条"
                        },
                        "auto_format_large": {
                            "type": "boolean",
                            "description": "数值>10000时自动格式化为'1.2万',默认true"
                        }
                    }
                },
                "insight": {
                    "type": "string",
                    "description": "图表解读(2-3句中文),必须基于实际数据。包含:1.最显著趋势(量化) 2.第二个发现 3.业务含义或异常"
                }
            },
            "required": ["chart_type","x_col","y_col","title",
                         "x_axis_label","y_axis_label","insight"]
        }
    }
}

【任务三: 实现各种图表】

实现 src/tools.py 中的 make_chart 函数:
- 调用 validate_chart_type 校验,发生降级时显示警告
- 用 Plotly Express + Graph Objects 实现各种图表
- 定义 COLOR_PALETTE 常量统一色板
- 图表用 st.plotly_chart(fig, use_container_width=True) 显示
- 图表下方用 st.info 显示 insight
- 图表下方加"查看原始数据" expander 展示 DataFrame

combo 双轴图实现要点:
- 用 plotly.graph_objects.Figure + make_subplots(specs=[[{"secondary_y": True}]])
- 左轴柱状图(绝对量),右轴折线图(百分比/率)
- 两轴颜色与对应系列颜色呼应

【在 AGENT_SYSTEM_PROMPT 中加入】

```
图表选择规则(代码层会自动校验,但请尽量选对):
- 不要用 3D 饼图(视觉失真)
- 类别 > 5 个不要用 pie/donut,改用 barh
- 时间序列优先 line,X 轴必须是时间字段
- 不同量级双指标(如订单量+转化率)用 combo 双轴图
- 不确定时优先 bar 或 table(最不容易出错)

调用 make_chart 时必须填 result_key,
明确说明要画哪次查询的数据,不要依赖默认值。
```

【测试用例(测试校验是否生效)】
1. 让 LLM 尝试用 pie 画 20 个品类 → 应该自动降级为 barh + 显示警告
2. 让 LLM 用 line 画分类字段(非时间) → 应该自动降级为 bar
3. 正常 bar 图 → 应该正常显示,无警告
4. combo 双轴图(订单量+转化率) → 两轴正确分配

【交付方式】
1. 先写 validators.py(完整实现,带单元测试)
2. 更新 tools.py 中的 make_chart Schema 和实现
3. 更新 prompts.py 中的图表选择规则
4. 边写边测试,每加一种图表类型就测一次
```

### 4.2 Day 18-21:归因诊断工具 [修订]

> ⚠️ **v2 修订说明(对应问题 3)**
>
> v1 把归因工具放在 Day 18-20(3天)。但这个工具内部需要:
> 动态 SQL 拼接 + 维度 JOIN + 贡献度计算 + 二次 LLM 调用,
> 实际难度被低估了。
>
> **主要风险点:** `metric_sql_template` 中的 `{time_filter}` 占位符
> 要求 LLM 正确生成 SQL 片段作为参数。DeepSeek 在生成"SQL 中的 SQL"
> 时容易出语法错误,比如忘记表别名、忘记 AND 连接条件等。
>
> **修复方案:**
> 1. 时间延长到 4 天(Day 18-21)
> 2. 预定义 5 个标准时间过滤模板作为 few-shot 示例,
>    LLM 参考模板填写,而不是从零生成 SQL 片段
> 3. 工具内部加 SQL 语法验证层

**📋 Prompt 模板:**

```
现在开始做归因诊断工具。这是 Week 3 最重要的部分,需要 4 天。

【背景】
"为什么 X 指标变了"是数据分析师最高频的工作,业内叫"归因分析"。
我们要把这个分析过程工程化成一个工具。

【Day 18: 先做时间过滤模板层(不写主工具)】

在 src/prompts.py 中加入时间过滤模板库:

TIME_FILTER_TEMPLATES = {
    "month_range": {
        "description": "按月份范围过滤",
        "template": "{date_col} >= '{start_year}-{start_month:02d}-01' AND {date_col} < '{end_year}-{end_month:02d}-01'",
        "example": "order_purchase_timestamp >= '2017-10-01' AND order_purchase_timestamp < '2018-01-01'"
    },
    "quarter": {
        "description": "按季度过滤",
        "template": "EXTRACT(YEAR FROM {date_col}) = {year} AND EXTRACT(QUARTER FROM {date_col}) = {quarter}",
        "example": "EXTRACT(YEAR FROM order_purchase_timestamp) = 2017 AND EXTRACT(QUARTER FROM order_purchase_timestamp) = 4"
    },
    "year": {
        "description": "按整年过滤",
        "template": "EXTRACT(YEAR FROM {date_col}) = {year}",
        "example": "EXTRACT(YEAR FROM order_purchase_timestamp) = 2017"
    },
    "last_n_days": {
        "description": "最近 N 天",
        "template": "{date_col} >= CURRENT_DATE - INTERVAL '{n}' DAY",
        "example": "order_purchase_timestamp >= CURRENT_DATE - INTERVAL '30' DAY"
    },
    "custom": {
        "description": "自定义范围",
        "template": "{date_col} BETWEEN '{start_date}' AND '{end_date}'",
        "example": "order_purchase_timestamp BETWEEN '2017-10-01' AND '2017-12-31'"
    }
}

同时在 diagnose_metric 工具的 description 中加入这些模板作为 few-shot 示例,
告诉 LLM: "填写 filter_sql 时,请参考以下标准格式..."

【归因诊断工具完整 Schema】

{
    "type": "function",
    "function": {
        "name": "diagnose_metric",
        "description": "对一个指标的变化进行多维度归因分析。当用户问'为什么X指标变了''X指标下跌的原因'时使用。\n\n⚠️ 填写 filter_sql 时必须参考以下标准格式:\n- 月份范围: \"order_purchase_timestamp >= '2017-10-01' AND order_purchase_timestamp < '2018-01-01'\"\n- 季度: \"EXTRACT(YEAR FROM order_purchase_timestamp) = 2017 AND EXTRACT(QUARTER FROM order_purchase_timestamp) = 4\"\n- 整年: \"EXTRACT(YEAR FROM order_purchase_timestamp) = 2017\"\n- 自定义: \"order_purchase_timestamp BETWEEN '2017-10-01' AND '2017-12-31'\"",
        "parameters": {
            "type": "object",
            "properties": {
                "metric_name": {
                    "type": "string",
                    "description": "要诊断的指标名,如'销售额'/'客单价'/'订单数'"
                },
                "base_sql": {
                    "type": "string",
                    "description": "指标的基础 SQL(不含时间过滤)。工具内部会自动拼接时间条件。\n例: 'SELECT SUM(price) as metric_value FROM order_items oi JOIN orders o ON oi.order_id = o.order_id'\n注意: 只写 SELECT 和 FROM/JOIN 部分,不要写 WHERE"
                },
                "date_column": {
                    "type": "string",
                    "description": "时间字段的完整引用,如 'o.order_purchase_timestamp'"
                },
                "period_a": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "如'2017 Q3'"},
                        "filter_sql": {"type": "string", "description": "时间过滤 SQL 片段(参考上方标准格式)"}
                    },
                    "required": ["label", "filter_sql"]
                },
                "period_b": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "如'2017 Q4'"},
                        "filter_sql": {"type": "string", "description": "时间过滤 SQL 片段"}
                    },
                    "required": ["label", "filter_sql"]
                },
                "drill_dimensions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dimension_name": {"type": "string", "description": "维度名,如'品类'"},
                            "dimension_col": {"type": "string", "description": "SQL 中的字段引用,如'p.product_category_name'"},
                            "extra_join": {"type": "string", "description": "如需额外 JOIN,写在这里,如'LEFT JOIN products p ON oi.product_id = p.product_id'"}
                        },
                        "required": ["dimension_name", "dimension_col"]
                    },
                    "description": "要下钻的维度列表,建议 3-5 个"
                },
                "decomposition_formula": {
                    "type": "string",
                    "description": "可选。指标分解公式,如'销售额 = 订单数 × 客单价'。有的话工具会先做分解再下钻。"
                }
            },
            "required": ["metric_name","base_sql","date_column","period_a","period_b","drill_dimensions"]
        }
    }
}

【工具内部实现逻辑(Day 19-20)】

def diagnose_metric(metric_name, base_sql, date_column, period_a, period_b,
                    drill_dimensions, decomposition_formula=None):
    """
    Step 1: SQL 语法预校验
    - 检查 base_sql 是否包含危险关键字(INSERT/UPDATE/DELETE)
    - 检查 period_a/b 的 filter_sql 是否非空
    - 如果校验失败,返回明确错误,不执行
    
    Step 2: 计算总体指标变化
    sql_a = f"{base_sql} WHERE {period_a['filter_sql']}"
    sql_b = f"{base_sql} WHERE {period_b['filter_sql']}"
    value_a = execute_and_get_single_value(sql_a)
    value_b = execute_and_get_single_value(sql_b)
    total_change = value_b - value_a
    
    Step 3: (可选) 指标分解
    if decomposition_formula:
        # 拆解为子指标分别计算
        pass
    
    Step 4: 各维度下钻
    dimension_results = []
    for dim in drill_dimensions:
        # 拼接带分组的 SQL
        dim_sql_a = f"""
            SELECT {dim['dimension_col']} as dimension_value,
                   SUM(...) as metric_value
            FROM (...) {dim.get('extra_join', '')}
            WHERE {period_a['filter_sql']}
            GROUP BY {dim['dimension_col']}
        """
        # 分别查两期,计算变化和贡献度
        contribution = (value_b_dim - value_a_dim) / abs(total_change) * 100
        dimension_results.append({...})
    
    Step 5: 找 Top 3 贡献因素
    
    Step 6: 调 LLM 生成中文归因结论
    conclusion = call_llm_for_conclusion(metric_name, overview, dimension_results)
    
    Step 7: 返回结构化结果
    return {
        "overview": {"period_a": ..., "period_b": ..., "change": ..., "change_pct": ...},
        "top_contributors": [...],   # Top 3 贡献因素
        "dimension_analysis": [...], # 各维度完整结果
        "conclusion": conclusion,    # LLM 生成的中文结论
        "confidence": "高/中/低",    # 基于规则评估
        "limitations": "...",        # 局限性说明
    }
    
    置信度评估规则(用代码,不用 LLM 自评):
    - 高: 总变化量 > 10%,Top 1 贡献因素占比 > 40%,数据量充足
    - 中: 总变化量 5-10%,或 Top 1 贡献不突出
    - 低: 总变化量 < 5%(可能是正常波动),或样本量少
    """
    pass

【Day 21: 接入 Agent + 测试】

1. 在 prompts.py 的 AGENT_SYSTEM_PROMPT 中加入:
```
当用户问"为什么 X 变了""X 下跌的原因"这类问题时,使用 diagnose_metric 工具。
使用前先确认:
- 指标定义(销售额是指价格之和?还是含运费?)
- 对比的两个时期(参考可用数据的时间范围)
- 下钻维度(基于业务理解,通常包括: 品类/地区/支付方式/用户等级)

填写 base_sql 时,只写 SELECT+FROM+JOIN 部分,不要写 WHERE。
填写 filter_sql 时,使用标准时间过滤格式(在工具描述里有示例)。

输出归因结论时,必须包括:
1. 总体变化量(数字+百分比)
2. Top 3 贡献因素(数字+百分比)
3. 置信度评估(工具自动计算,你不要修改)
4. 局限性说明(哪些因素没有数据支撑)
5. 建议下一步动作(具体可执行)
```

2. 测试场景:
   - "2018年1月销售额比2017年12月下跌了,为什么?"
   - "为什么 SP 州的订单量比 RJ 州多这么多?"
   - 验证 filter_sql 各种格式是否正确生成

3. 验证点:
   - 贡献度计算是否正确(手动验算前 3 条)
   - 置信度评估是否合理
   - SQL 拼接是否有语法错误

【交付方式】
Day 18: validators.py 中的时间模板层 + 工具 Schema 更新
Day 19-20: diagnose_metric 核心实现(含 SQL 校验、贡献度计算)
Day 21: 接入 Agent + System Prompt 更新 + 完整测试
```

### 4.3 Day 22:主动洞察 + 报告生成(含 Word 导出) [修订]

> ⚠️ **v2 修订说明(对应问题 5)**
>
> v1 的报告只能生成 Markdown,在 Streamlit 里看很好,
> 但发给领导/同事时没人用 Markdown 文件,需要 Word。
>
> **修复方案:** 在 generate_report 工具上加 `output_format` 参数,
> 用 `python-docx` 把 Markdown 内容转成格式化的 Word 文档。
> 成本很低(一两天工作量),但实用价值大幅提升。

**📋 Prompt 模板:**

```
最后三个功能,做完 Week 3 就完整了。

【任务 1: 主动洞察】

修改 prompts.py 的 AGENT_SYSTEM_PROMPT,加入:
```
完成每一轮分析后,主动推荐下一步可深挖的方向。

推荐格式:
"基于本轮分析,我注意到几个值得深入的方向:
[1] {方向1}: {具体理由,引用数据}
[2] {方向2}: {具体理由,引用数据}
[3] {方向3}: {具体理由,引用数据}
请告诉我你想深挖哪个,或者继续问其他问题。"

规则:
- 优先推荐发现的异常点(带具体数字)
- 优先推荐有业务价值的方向
- 不超过 3 个建议
- 用数字编号方便用户快速选择
- 不要重复推荐上一轮已经分析过的方向
```

【任务 2: 报告生成工具(含 Word 导出)】

新增 generate_report 工具:

{
    "type": "function",
    "function": {
        "name": "generate_report",
        "description": "把当前会话的所有分析整合成完整报告,支持 Markdown 展示和 Word 文件下载",
        "parameters": {
            "type": "object",
            "properties": {
                "report_title": {
                    "type": "string",
                    "description": "报告标题,如'2017年Q4销售分析周报'"
                },
                "include_sections": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["背景","核心发现","详细分析","归因结论","建议","附录"]
                    }
                },
                "audience": {
                    "type": "string",
                    "enum": ["management","operation","technical"],
                    "description": "management: 管理层,简洁结论优先 / operation: 运营,可执行建议优先 / technical: 技术,方法论细节"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "word", "both"],
                    "description": "输出格式。markdown: 在页面展示; word: 只生成下载文件; both: 两者都要(默认)",
                    "default": "both"
                }
            },
            "required": ["report_title", "include_sections"]
        }
    }
}

实现要求:

def generate_report(report_title, include_sections,
                    audience="operation", output_format="both"):
    """
    1. 从 session_state 读取所有历史分析:
       - messages 中的对话历史
       - query_results 中的所有查询结果
    
    2. 调用 LLM 生成 Markdown 内容(根据 audience 调整风格)
    
    3. 如果 output_format in ("markdown", "both"):
       - st.markdown(content) 渲染
    
    4. 如果 output_format in ("word", "both"):
       - 调用 markdown_to_word(content, report_title) 生成 .docx
       - st.download_button("下载 Word 报告", data=docx_bytes,
                            file_name=f"{report_title}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    """
    pass

def markdown_to_word(markdown_content: str, title: str) -> bytes:
    """
    用 python-docx 把 Markdown 转成格式化的 Word 文档。
    
    格式要求:
    - 文档标题: 24pt 加粗居中
    - 一级标题(#): 18pt 加粗,段前间距 12pt
    - 二级标题(##): 14pt 加粗,段前间距 8pt
    - 正文: 11pt,行间距 1.3 倍
    - 表格: 有边框,表头行加灰色底色
    - 加粗文本(**text**): 对应 Word 加粗
    - 项目符号列表(-): 转换为 Word 项目符号段落
    - 页眉: 文档标题
    - 页脚: 生成日期 + 页码
    
    返回 bytes(用于 st.download_button)
    """
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    import re
    from io import BytesIO
    
    doc = Document()
    # ... 实现 Markdown → Word 转换逻辑
    
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()

【任务 3: 优化 AGENT_SYSTEM_PROMPT】

把 prompts.py 中的 AGENT_SYSTEM_PROMPT 整理成最终版(参考附录 A)。

【交付方式】
1. 先实现 markdown_to_word,测试几段 Markdown 能否正确转换
2. 然后完整实现 generate_report
3. 给我一份完整的 prompts.py 最终版
4. 测试:输入"生成本次分析的 Word 报告",能下载 .docx 文件
```

**✅ Week 3 完成标志:**
- 图表有自动校验,LLM 选错类型会自动降级并显示提示
- make_chart 用 result_key 精确指定数据,不会画错历史数据
- 归因诊断工具能正确计算贡献度,置信度由代码评估而非 LLM 自评
- 主动洞察在每轮分析后推荐具体的下一步
- 能生成 Word 格式的分析报告并下载

---

## 五、Week 4 · 求职作品包装

不写代码,做"营销"。这是项目对求职最有杠杆的部分。

### 5.1 Day 23:部署上线

```bash
# 1. 整理 requirements.txt
pip freeze > requirements.txt

# 2. 推 GitHub
git init
git add .
git commit -m "feat: AI data analyst agent v1.0"
git remote add origin https://github.com/{你的用户名}/ai-data-agent.git
git push -u origin main

# 3. Streamlit Community Cloud 一键部署
# 访问 share.streamlit.io,绑定 GitHub 即可
# 注意把 DEEPSEEK_API_KEY 加到 Streamlit Secrets
```

### 5.2 Day 24-25:GitHub README

README 必须包含:
1. **项目简介(2-3 句)**:解决什么问题、给谁用
2. **在线 Demo 链接**:让面试官能直接体验
3. **架构图**:把本文档第 1 节的架构图放进去
4. **核心场景演示**:3 个 GIF 动图(用 [Kap](https://getkap.co/) 录制)
5. **技术选型说明**:为什么选 DeepSeek / 不用 LangChain / 用 DuckDB
6. **为什么不直接用 Claude/Gemini**:专门写这一节(参考对话记录里的 5 个区别)
7. **未来改进方向**:展示你有产品视角

### 5.3 Day 26-27:技术复盘文章

发到掘金 + 知乎 + 小红书。标题参考:
- "数据分析师如何用 AI 重构自己的工作流:一个 Agent 项目实践"
- "为什么我没用 LangChain,从零写了一个数据分析 Agent"
- "3.5 年数据分析师的 AI 转型实验"

**文章结构:**
1. 我为什么做这个(业务痛点)
2. 我怎么设计的(架构图 + 关键决策)
3. 踩过的 3 个坑(这里就用手册里修复的 5 个问题作为素材!)
4. 效果展示(实际 demo)
5. 局限和未来

### 5.4 Day 28:录 Demo 视频

3-5 分钟,结构:
- 0:00-0:30 项目背景
- 0:30-2:30 演示 3 个核心场景(基础查询 / 多步分析 / 归因诊断)
- 2:30-3:30 技术架构 1 分钟讲清
- 3:30-4:30 业务价值 + 反思
- 4:30-5:00 总结

### 5.5 Day 29:简历更新 + 面试准备

**简历项目描述模板:**

```
AI 数据分析 Agent | 个人项目 | 2026.X
个人开发的数据分析师 AI 助手,能通过自然语言完成数据查询、可视化、归因分析全流程。

技术栈: Python | Streamlit | DeepSeek API | DuckDB | Plotly | python-docx
GitHub: github.com/xxx | Demo: xxx.streamlit.app

核心亮点:
• 设计 Agent 架构,通过 Function Calling 实现工具调用 + 多步规划 + 多轮记忆
• 用带意图标签的查询缓存机制解决跨轮数据污染问题,确保图表数据准确
• 用 DuckDB 作为统一查询层,支持 Excel / CSV / 数据库的统一 SQL 访问
• 实现归因诊断工具,自动完成指标拆解 + 维度下钻 + 贡献度量化(置信度由代码评估)
• 加入图表类型自动校验层,防止 LLM 选错图表类型
• 支持一键生成 Word 分析报告并下载
```

**面试话术准备 7 个问题:**

1. 这个项目的设计思路是什么?
2. 为什么选 DeepSeek?为什么不用 LangChain?
3. 如何让 Agent 能处理复杂多步问题?
4. 归因诊断工具内部是怎么工作的?
5. 这个 Agent 的局限性是什么?如果在公司落地怎么改进?
6. **你在做这个项目过程中发现了哪些设计问题,怎么修复的?**
7. **为什么不直接把数据传给 Claude/Gemini 来分析?**

> 问题 6 和 7 是 v2 新增的,这两个问题能展示你的工程反思能力和系统性思维,是加分项。

每个问题准备 1-2 分钟的回答,**对着镜子练 3 遍**。

---

## 六、附录 A · Agent System Prompt 最终版

把这段保存为 `src/prompts.py` 中的 `AGENT_SYSTEM_PROMPT`:

```python
AGENT_SYSTEM_PROMPT = """
你是一个专业的数据分析师 AI Agent,帮助用户完成数据查询、可视化和深度分析。

## 你的能力
你可以调用以下工具:
1. query_database: 执行 SQL 查询(结果会带意图标签存入缓存)
2. make_chart: 生成 Plotly 交互式图表(图表类型有自动校验)
3. analyze_dataframe: 做基础统计分析
4. diagnose_metric: 多维度归因诊断
5. generate_report: 生成分析报告(支持 Word 下载)

## 工作原则

### 简单问题
对于明确的查询(如"2017年总销售额"),直接调 query_database,然后视情况调 make_chart。

### 复杂多步问题
对于需要多步骤的问题,你必须:
1. 先用一段话说明"分析计划"(不调用工具,只输出文本)
   格式: "分析计划: 我将分 N 步完成——第一步...第二步..."
2. 然后逐步调用工具执行
3. 每一步执行后,简要说明这一步的发现(1-2 句)
4. 全部完成后,综合所有发现给出最终结论

### 归因诊断问题
当用户问"为什么 X 变了""X 下跌的原因"时,使用 diagnose_metric 工具。
使用前先确认:
- 指标定义(如"销售额是指 price 之和还是含运费")
- 对比的两个时期
- 要下钻的维度(基于业务理解,通常: 品类/地区/支付方式)

填写 base_sql 只写 SELECT+FROM+JOIN 部分,不要写 WHERE。
填写 filter_sql 使用工具描述里的标准时间格式。

输出归因结论时必须包括:
- 总体变化量(数字+百分比)
- Top 3 贡献因素(数字+贡献占比)
- 置信度(工具自动计算,不要修改)
- 局限性说明
- 建议下一步动作

### 模糊问题处理
如果用户问题模糊,先澄清再执行。
例: "近期销售如何?" → 先问:"'近期'是指最近7天、30天,还是本月?"

## 关键约束

### 数据来源指定
每次调用 make_chart 或 analyze_dataframe,必须通过 result_key 明确指定
用哪次查询的数据。result_key 对应 query_database 调用时的 intent 参数。
不要依赖默认值,尤其是跨轮对话时。

### 图表选择
代码层会自动校验图表类型,但请尽量选对:
- 时间序列用 line(X 轴必须是时间字段)
- 分类对比 ≤8 类用 bar,>8 类或名字长用 barh
- 占比 ≤5 类用 pie/donut
- 不同量级双指标用 combo
- 不确定时优先 bar 或 table

## 主动洞察

每完成一轮分析,主动推荐下一步:
"基于本轮分析,我注意到几个值得深入的方向:
[1] {方向1}: {理由,引用具体数字}
[2] {方向2}: {理由}
[3] {方向3}: {理由}
请告诉我你想深挖哪个,或者继续问其他问题。"

规则:
- 优先推荐发现的异常点(带具体数字)
- 不超过 3 个建议
- 不要重复上一轮已分析过的方向

## 上下文使用

充分利用对话历史:
- 用户说"那""这个"等代词时,正确指向之前的内容
- 用户定义过的术语(如"活跃用户=最近30天有下单")要沿用,不要重新询问
- 已查过的数据(query_results 中有记录)不要重复查,直接引用

## 边界与诚实

- 数据没有的字段不要编造(如数据没有渠道字段,不要凭空做渠道分析)
- 归因结论要标注置信度(由工具计算得出)和局限性
- 如果用户问题超出能力范围,坦诚告知并说明原因

## 安全约束

- 只生成 SELECT,绝不生成 INSERT/UPDATE/DELETE/DROP
- 涉及敏感字段(手机号、邮箱)时自动脱敏
- 不执行没有 WHERE 条件的全表扫描(除非用户明确要求)
"""
```

---

## 七、附录 B · 调试与优化建议

### 常见问题排查

**Q: make_chart 画出了上一轮查询的数据怎么办?**

A: 这是 v1 的已知问题,v2 已修复。检查:
1. `query_database` 调用时是否传了有意义的 `intent` 参数
2. `make_chart` 调用时是否传了 `result_key`
3. System Prompt 里是否有"必须指定 result_key"的要求

**Q: DeepSeek 返回的 tool_calls 为空怎么办?**

A: 几种可能:
1. 用户问题不需要工具(纯聊天) → 正常
2. tools 描述写得不够清晰 → 优化 description
3. temperature 太低 → 调到 0.3-0.5
4. 加一句:"如果需要查询数据,必须调用工具,不要凭记忆回答"

**Q: 归因工具的 SQL 拼接出语法错误怎么办?**

A: 检查:
1. `base_sql` 是否包含了 WHERE(不应该包含)
2. `filter_sql` 是否用了标准时间格式(参考模板库)
3. `extra_join` 是否正确(JOIN 语句不要重复)
4. 在工具内部加 try-except,SQL 失败时打印完整 SQL 便于调试

**Q: SQL 经常生成错怎么办?**

A: 检查:
1. schema 是否完整传给了 LLM(包括字段类型、表关系)
2. 是否提供了 few-shot 示例
3. 复杂 JOIN 时 schema 注释是否说明了关联关系

**Q: 多轮对话上下文丢失?**

A: 检查 messages 数组是否完整传递,特别是 tool message 不能截断 tool_call_id。

**Q: Agent 死循环怎么办?**

A: agent.py 主循环必须有 MAX_ITERATIONS 限制(建议 12),超过就强制退出并告知用户。

### 性能优化

1. **对话历史压缩**:超过一定长度时,用 LLM 总结早期对话,替换原始 tool messages
2. **SQL 结果缓存**:相同 SQL 不重复执行,比较 query_results 里的 sql 字段
3. **流式输出**:用 `stream=True` 让回答边生成边显示,提升体验
4. **并行工具调用**:DeepSeek 支持 parallel tool calls,可同时调多个查询

---

## 八、检查清单

完成项目前,确认以下事项都做完:

### 功能完整性
- [ ] 能上传 Excel/CSV 并查询
- [ ] 能查询预置 Olist 数据集
- [ ] 至少 7 种图表类型可用
- [ ] 图表类型校验层生效(饼图 >5 类自动降级)
- [ ] make_chart 用 result_key 指定数据源
- [ ] 能处理多步分析问题
- [ ] 归因诊断工具能跑通(含贡献度计算)
- [ ] 置信度由代码规则评估,不是 LLM 自评
- [ ] 能生成 Word 报告并下载
- [ ] 多轮对话上下文连贯
- [ ] 只有大查询(>10万行)才弹确认框
- [ ] 错误能友好提示

### 工程质量
- [ ] 代码有详细注释
- [ ] 关键函数有 docstring
- [ ] requirements.txt 包含 python-docx
- [ ] validators.py 有单元测试
- [ ] .env.example 存在
- [ ] .gitignore 排除敏感文件

### 求职准备
- [ ] 项目部署上线,有公开 URL
- [ ] GitHub README 包含"为什么不直接用 Claude/Gemini"一节
- [ ] 至少 1 篇技术复盘文章发布
- [ ] 3-5 分钟 demo 视频录制完成
- [ ] 简历项目描述写好(含 v2 修复的亮点)
- [ ] 7 个面试问题准备好(含问题 6 和 7)

---

完成所有这些,你就有了一个完整的、能讲能演示的 AI 数据分析 Agent 求职作品。

祝你拿到心仪的 offer 🎯
