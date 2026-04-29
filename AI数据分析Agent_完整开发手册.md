# AI 数据分析 Agent · 完整开发手册

> 适用对象:有 SQL + Pandas 基础,使用 Claude Code 辅助开发的数据分析师
> LLM 选型:DeepSeek-V3 (deepseek-chat)
> 预计工期:4 周(每周约 10-15 小时)

---

## 一、项目概览

### 1.1 项目目标

构建一个面向数据分析师工作场景的 AI Agent,能够通过自然语言完成:
- 多源数据查询(Excel / CSV / Olist 数据集 / 远程数据库)
- 自动数据可视化
- 多步深度分析(包括归因诊断)
- 自动生成分析报告

### 1.2 技术栈

| 模块 | 选型 | 备注 |
|---|---|---|
| 前端 | Streamlit | 半天上手,纯 Python |
| LLM | DeepSeek-V3 (deepseek-chat) | 通过 OpenAI SDK 调用 |
| Agent 编排 | 原生 Function Calling | 不用 LangChain |
| 数据存储与查询 | DuckDB | SQL 统一访问多源 |
| 数据处理 | Pandas | 辅助 |
| 可视化 | Plotly | 交互式图表 |
| 部署 | Streamlit Community Cloud | 免费 |

### 1.3 环境准备

```bash
pip install streamlit duckdb pandas plotly openai python-dotenv openpyxl
```

`.env` 文件:
```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

### 1.4 项目目录结构

```
ai-data-agent/
├── .env                      # API key
├── requirements.txt          # 依赖
├── README.md                 # 项目说明(求职用)
├── data/
│   ├── olist.db             # DuckDB 数据库
│   └── raw/                 # 原始 CSV
├── src/
│   ├── app.py               # Streamlit 主程序
│   ├── agent.py             # Agent 核心:LLM 调用 + 工具循环
│   ├── tools.py             # 工具定义(SQL查询/图表/分析/归因)
│   ├── data_source.py       # 数据源抽象层
│   ├── prompts.py           # System Prompt 模板
│   └── config.py            # 配置(模型名、API 地址等)
├── scripts/
│   └── init_db.py           # 数据初始化脚本
└── docs/
    └── architecture.png     # 架构图(放 README 里)
```

### 1.5 4 周路线图

| 周次 | 目标 | 交付物 |
|---|---|---|
| Week 1 | 跑通 NL2SQL 最短链路 | 能用自然语言查数据 + 显示结果 |
| Week 2 | 升级为真正的 Agent | 能调用工具 + 多步规划 + 多轮记忆 |
| Week 3 | 加深度能力 | 智能图表 + 归因诊断 + 主动洞察 |
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
   - 表名用文件名去掉后缀和 "olist_" 前缀(如 olist_orders_dataset.csv → orders)
   - 加载完成后打印各表的行数和字段数
   - 如果 olist.db 已存在,先删除再重建

2. 写 src/data_source.py:
   抽象数据源模块,包含一个 DataSource 类,提供这些方法:
   - __init__(db_path): 连接 DuckDB
   - get_schema() -> str: 返回所有表的 schema 文本(给 LLM 看)
   - load_uploaded_file(file): 把 Streamlit 上传的 Excel/CSV 注册成 DuckDB 临时表
   - query(sql) -> pandas.DataFrame: 执行 SQL 返回 DataFrame
   - list_tables() -> list[str]: 返回当前所有可查表名

3. 写 src/app.py:
   Streamlit 主程序,要有:
   - 页面标题: "AI 数据分析 Agent"
   - 左侧 sidebar: 
     * 显示当前 schema(用 st.expander 折叠)
     * 文件上传组件(支持 .xlsx 和 .csv,可多文件)
     * 上传后调用 data_source.load_uploaded_file
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
   - 用户输入 → 调用 DeepSeek API
   - 显示 LLM 生成的 SQL(用 st.code 在 expander 里折叠)
   - 加一个"确认执行"按钮
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

### 2.4 Day 7:加确认机制 + Schema 优化

**📋 Prompt 模板:**

```
现在要让 NL2SQL 更可靠,加几个体验和可靠性优化。

【任务】

1. 改进 SQL 生成:
   - 在 SYSTEM_PROMPT 里加上 schema 中重要表的"关系说明"(用注释方式)
   - 例如: "-- orders 表通过 customer_id 关联 customers 表"
   - 把这部分做成 data_source.get_schema_with_relationships()

2. SQL 确认卡片改进:
   显示给用户的不只是 SQL,还要:
   - 查询意图描述(用 LLM 生成一句中文说明)
   - 涉及的表名列表
   - 是否包含 JOIN 操作
   - 预估返回行数(可选: 用 EXPLAIN 或简单的 COUNT)

3. 历史 SQL 记录:
   - 在 sidebar 加 "最近查询" 列表(用 st.session_state 保存)
   - 点击历史项可以重新执行

【交付方式】
单独输出每个改动,用 diff 风格说明改了哪里。
```

**✅ Week 1 完成标志:**
有一个能用中文问问题、自动出 SQL、显示意图、可以确认执行、能看到历史的 NL2SQL 工具。这时候它还不算 Agent,但已经能 demo 了。

---

## 三、Week 2 · 升级为 Agent (Function Calling)

### 3.1 Day 8-9:理解 DeepSeek Function Calling

**📋 Prompt 模板(让 Claude Code 教你):**

```
我已经做完了基础的 NL2SQL 工具。现在要把它升级成一个真正的 Agent,核心是引入 DeepSeek 的 Function Calling 能力。

请先不要写代码,先解释清楚以下问题(用我能听懂的话,可以打比方):

1. DeepSeek 的 Function Calling 和普通 API 调用有什么区别?
2. 一个完整的 Agent 循环长什么样?(请画一个文字流程图)
3. tools 参数怎么定义?给我一个最简单的例子(比如定义一个 add(a, b) 工具)
4. LLM 返回 tool_calls 后,我的代码要做什么?把结果传回 LLM 时怎么传?
5. 如果 LLM 一次决定调多个工具(parallel tool calls),怎么处理?
6. DeepSeek Function Calling 有哪些常见坑?(比如假调用、JSON 不合法等)

回答完后,我们再开始改代码。
```

### 3.2 Day 10-11:重构成 Agent 架构

**📋 Prompt 模板:**

```
现在开始重构。目标是把当前的 NL2SQL 升级成一个真正的 Agent。

【架构调整】

1. 新建 src/tools.py,定义这 3 个工具(Week 2 先做这 3 个):

   工具 1: query_database
   - 功能: 执行 SQL 查询,返回 DataFrame 的描述(行数、列名、前 5 行预览)
   - 不直接返回完整 DataFrame(LLM 不需要看全部数据,会浪费 token)
   - 把执行结果存到 st.session_state['last_result'] 供后续工具使用
   
   工具 2: make_chart
   - 功能: 根据上一步 query_database 的结果,画图
   - 参数: chart_type, x_col, y_col, title 等(Week 3 会扩展更多参数)
   - 用 Plotly 画,通过 st.plotly_chart 显示
   
   工具 3: analyze_dataframe
   - 功能: 对上一步结果做基础统计分析
   - 参数: analysis_type ("describe" | "correlation" | "groupby_summary")
   - 返回分析结果的文字描述

2. 重写 src/agent.py,实现 Agent 主循环:
   
   def run_agent(user_message: str, history: list) -> str:
       """
       Agent 主循环:
       1. 构造 messages(system + history + user_message)
       2. 调 LLM,带上 tools 参数
       3. 如果 LLM 返回 tool_calls:
          a. 解析每个 tool_call 的工具名和参数
          b. 调用对应的 Python 函数,拿到结果
          c. 把结果作为 tool message 加到 messages
          d. 再调 LLM,继续循环
       4. 如果 LLM 返回最终回答(没有 tool_calls),退出循环,返回回答
       5. 加最大循环次数限制(如 10 次),防止死循环
       """

3. 修改 src/app.py:
   - 用户输入直接调 run_agent(),不再走 NL2SQL 旧流程
   - 在 UI 上展示 Agent 的"思考过程": 
     * 每次 tool_call 显示 "🔧 正在调用工具: {tool_name}"
     * 工具结果用 expander 折叠展示
     * 最终回答正常显示

【DeepSeek Function Calling 示例代码】

from openai import OpenAI

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

tools = [
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "执行 SQL 查询,返回结果概要",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的 SQL 语句(只能是 SELECT)"
                    },
                    "intent": {
                        "type": "string",
                        "description": "用一句中文说明这个查询的意图"
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
    tool_choice="auto"
)

# 检查是否有 tool_calls
message = response.choices[0].message
if message.tool_calls:
    for tool_call in message.tool_calls:
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        # 执行工具...
        result = execute_tool(function_name, function_args)
        # 把结果加进 messages
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": str(result)
        })

【DeepSeek 特别注意事项】
- DeepSeek 偶尔会"假调用"(说要调工具但 tool_calls 是空),要做容错
- arguments 是 JSON 字符串,记得 json.loads,且要 try-except 处理解析失败
- temperature 建议设 0.3-0.5(完全 0 会让 Agent 缺少灵活性,太高会乱选工具)
- 对话历史里的 tool message 会占用大量 token,要定期清理或截断

【交付方式】
1. 先给我看 tools.py 的工具定义(只是定义,不实现)
2. 我确认 Schema 后再写实现
3. 然后写 agent.py 主循环
4. 最后改 app.py
每写一步,告诉我做了什么决策、为什么
```

### 3.3 Day 12-13:多步分析能力

**📋 Prompt 模板:**

```
现在 Agent 已经能调单个工具了。下一步让它能处理需要多步骤的复杂问题。

【目标场景】
用户问: "2017 年 Q4 哪个品类销售额下跌最严重?"

Agent 应该自动规划成:
Step 1: query_database (查 Q3 各品类销售)
Step 2: query_database (查 Q4 各品类销售)
Step 3: analyze_dataframe (计算环比,排序找出下跌最严重的)
Step 4: make_chart (画对比图)
Step 5: 输出结论

【任务】

1. 修改 src/prompts.py 中的 AGENT_SYSTEM_PROMPT:
   - 加入"分析规划"的要求
   - 让 LLM 在做复杂任务前,先输出一段"分析计划"(用普通文本)
   - 然后按计划执行,每一步执行完简要说明发现
   - 全部完成后,综合输出结论

   关键 Prompt 片段:
   ```
   当用户问的问题需要多步骤完成时,你必须:
   1. 先用一段话说明你的分析计划(不调用工具,只输出文本)
   2. 然后逐步调用工具执行
   3. 每一步执行后,简要说明这一步发现了什么
   4. 全部完成后,综合所有发现给出最终结论
   ```

2. 修改 src/app.py:
   - 用更清晰的 UI 展示多步执行过程
   - 每个 tool_call 显示步骤号 (Step 1, Step 2...)
   - 用 st.status 组件展示进度

【交付方式】
1. 先改 Prompt,我用 3 个简单到复杂的问题测试一下效果
2. 测试通过后再优化 UI
```

### 3.4 Day 14:多轮记忆 + 上下文管理

**📋 Prompt 模板:**

```
最后一步是让 Agent 真正"记得"之前的对话。

【任务】

1. 在 src/agent.py 中:
   - 把对话历史完整传给 LLM(messages 数组)
   - 但要做 token 管理: 
     * 如果 messages 总长度 > 50000 字符,截断最早的几轮对话
     * 始终保留 system message 和最新 5 轮对话
     * 工具调用结果占空间最大,优先截断旧的 tool message

2. 在 src/prompts.py 中加上下文使用规则:
   ```
   你能看到完整的对话历史。请充分利用历史信息:
   - 用户说"那再看看华南地区"时,"那"指的是上一轮的分析
   - 用户定义过的术语(如"活跃用户=最近30天有下单")要记住,后续沿用
   - 已经查过的数据,不要重复查询,直接引用
   ```

3. 在 src/app.py 加"清空对话"按钮(放 sidebar)

【测试场景】
对话 1: "查一下 2017 年总销售额"
对话 2: "那分到各个州看呢?"
对话 3: "Top 5 个州具体是哪些?"
Agent 应该正确理解"那""各个州""Top 5"都是基于第一句的上下文。

完成后简单测试一下三轮对话是否连贯。
```

**✅ Week 2 完成标志:**
- Agent 能自主选择调用 SQL/图表/分析工具
- 能处理需要多步执行的复杂问题
- 多轮对话能理解上下文(代词、引用)
- UI 上能看到 Agent 的思考和执行过程

---

## 四、Week 3 · 智能图表 + 归因诊断 + 主动洞察

### 4.1 Day 15-17:智能图表系统

**📋 Prompt 模板:**

```
现在要把图表能力做深。Week 2 的 make_chart 只是基础版,这周做完整版。

【完整图表工具 Schema 定义】

请把 src/tools.py 中的 make_chart 工具改成下面这个完整 Schema:

{
    "type": "function",
    "function": {
        "name": "make_chart",
        "description": "根据上一步 query_database 的结果生成 Plotly 交互式图表。请根据数据特征自动选择最合适的图表类型,选择规则见下方说明。",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["line", "bar", "barh", "pie", "donut", "scatter", "heatmap", "area", "combo", "table"],
                    "description": "图表类型。选择规则:\n- line: 时间序列趋势\n- bar: 分类对比(类别 ≤ 8 个)\n- barh: 横向条形图(类别名长 或 > 8 个)\n- pie/donut: 构成占比(类别 ≤ 5 个,占比加起来 100%)\n- scatter: 两个连续变量的相关性\n- heatmap: 二维交叉(如各城市各品类)\n- area: 累积量或占比变化\n- combo: 双轴图(柱+线,不同单位)\n- table: 精确数值查阅"
                },
                "x_col": {
                    "type": "string",
                    "description": "X 轴字段名(必须是上一步查询结果的列名)"
                },
                "y_col": {
                    "type": "string",
                    "description": "Y 轴字段名;饼图时是数值列"
                },
                "y_col_2": {
                    "type": "string",
                    "description": "复合图(combo)的第二个 Y 轴字段;其他图表不用填"
                },
                "color_col": {
                    "type": "string",
                    "description": "用于多系列着色的分类字段,可选"
                },
                "title": {
                    "type": "string",
                    "description": "图表标题(中文,必须包含时间维度,如 '2017 年各渠道月度 GMV 对比')"
                },
                "x_axis_label": {
                    "type": "string",
                    "description": "X 轴标题(带单位,如 '月份' / '城市')"
                },
                "y_axis_label": {
                    "type": "string",
                    "description": "Y 轴标题(带单位,如 '销售额(元)' / '订单数')"
                },
                "y_axis_label_2": {
                    "type": "string",
                    "description": "复合图第二 Y 轴标题"
                },
                "format_options": {
                    "type": "object",
                    "properties": {
                        "show_values": {
                            "type": "boolean",
                            "description": "是否在数据点上显示数值标签,默认 true(柱图、饼图自动开启)"
                        },
                        "thousand_separator": {
                            "type": "boolean",
                            "description": "数值是否用千分位逗号,默认 true"
                        },
                        "auto_format_large": {
                            "type": "boolean",
                            "description": "数值大于 10000 时是否自动格式化为 '1.2万',默认 true"
                        },
                        "sort_by": {
                            "type": "string",
                            "enum": ["x_asc", "x_desc", "y_asc", "y_desc", "none"],
                            "description": "排序方式;Top N 场景用 y_desc"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "限制显示前 N 条,Top N 场景用"
                        }
                    },
                    "description": "格式化选项,可选"
                },
                "insight": {
                    "type": "string",
                    "description": "图表解读(2-3 句中文),必须基于实际数据。包括:1.最显著的趋势或差异(量化) 2.第二个值得关注的点 3.业务含义或异常提示"
                }
            },
            "required": ["chart_type", "x_col", "y_col", "title", "x_axis_label", "y_axis_label", "insight"]
        }
    }
}

【实现要求】

1. 在 src/tools.py 中实现 make_chart 函数:
   - 用 Plotly Express + Plotly Graph Objects 实现各种图表
   - 颜色用统一的色板,定义为常量 COLOR_PALETTE
   - 数值格式化要遵循 format_options
   - 图表渲染用 st.plotly_chart(fig, use_container_width=True)
   - 图表下方显示 insight(用 st.info)
   - 图表下方加一个 "查看原始数据" 的 expander,展示 DataFrame

2. 实现 combo 图(双轴):
   - 用 plotly.graph_objects.Figure
   - 左轴柱状图,右轴折线图
   - 两个轴的颜色和对应系列颜色呼应
   - 例: 柱状(订单量,左轴蓝色)+ 折线(转化率%,右轴橙色)

3. 实现 heatmap:
   - 用于二维数据(如 城市 × 品类 → 销售额)
   - 用 px.imshow 或 px.density_heatmap
   - 颜色用 Sequential 色板(浅到深)

4. 在 prompts.py 的 AGENT_SYSTEM_PROMPT 中加入图表选择指引:
   ```
   选择图表类型时,遵循这些原则:
   - 不要画 3D 饼图(视觉失真)
   - 类别超过 5 个不要用饼图,改用柱图
   - 时间序列优先用 line,跨度 > 12 个月可考虑加移动平均
   - 对比量级差异大的指标(如订单量 vs 转化率)用 combo 双轴图
   - 不确定时,优先用 bar 或 table(最不容易出错)
   ```

【测试用例】
请基于这 5 个 query 测试图表选择是否合理:
1. "2017 年每月销售额" → 应该选 line
2. "Top 10 销售品类" → 应该选 barh
3. "支付方式占比" → 应该选 pie 或 donut
4. "各月订单量和转化率" → 应该选 combo
5. "各州各品类销售矩阵" → 应该选 heatmap

【交付方式】
1. 先给我看 tools.py 中 make_chart 的实现框架
2. 我确认后再写各个图表类型的具体实现
3. 边写边测试,每加一种图表类型就测一次
```

### 4.2 Day 18-20:归因诊断工具(项目最大亮点)

**📋 Prompt 模板:**

```
这是 Week 3 最重要的部分: 加入"归因诊断"能力。这是 Agent 的核心差异化能力。

【背景】
"为什么 X 指标变了"是数据分析师最高频的工作之一,业内叫"归因分析"或"诊断式分析"。
我们要做一个 diagnose_metric 工具,让 Agent 能自动完成多维度归因。

【完整归因诊断工具 Schema】

{
    "type": "function",
    "function": {
        "name": "diagnose_metric",
        "description": "对一个指标的变化进行多维度归因分析。当用户问'为什么 X 指标变了''X 指标下跌的原因是什么'这类诊断式问题时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "metric_name": {
                    "type": "string",
                    "description": "要诊断的指标名,如 '销售额' / '用户流失率' / 'GMV' / '客单价'"
                },
                "metric_sql_template": {
                    "type": "string",
                    "description": "指标的 SQL 计算模板,使用 {time_filter} 占位符表示时间过滤。\n例: 'SELECT SUM(price) FROM orders WHERE {time_filter}'\n注意: 时间过滤条件一定要用占位符,不要写死"
                },
                "period_a": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "description": "对照期标签,如 '2017 Q3'"
                        },
                        "filter_sql": {
                            "type": "string",
                            "description": "对照期的 SQL 过滤条件,如 \"order_purchase_timestamp BETWEEN '2017-07-01' AND '2017-09-30'\""
                        }
                    },
                    "required": ["label", "filter_sql"]
                },
                "period_b": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "description": "目标期标签,如 '2017 Q4'"
                        },
                        "filter_sql": {
                            "type": "string",
                            "description": "目标期的 SQL 过滤条件"
                        }
                    },
                    "required": ["label", "filter_sql"]
                },
                "drill_dimensions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dimension_name": {
                                "type": "string",
                                "description": "维度名,如 '品类' / '州' / '支付方式'"
                            },
                            "dimension_sql": {
                                "type": "string",
                                "description": "维度的 SQL 表达式,如 'product_category_name' / 'customer_state'"
                            },
                            "join_sql": {
                                "type": "string",
                                "description": "如果维度需要 JOIN 其他表,在这里写 JOIN 子句;不需要则留空"
                            }
                        },
                        "required": ["dimension_name", "dimension_sql"]
                    },
                    "description": "要下钻的维度列表,建议 3-5 个"
                },
                "decomposition_formula": {
                    "type": "string",
                    "description": "指标分解公式(可选)。如 '销售额 = 订单数 × 客单价'。如果有,会先做指标分解再下钻"
                }
            },
            "required": ["metric_name", "metric_sql_template", "period_a", "period_b", "drill_dimensions"]
        }
    }
}

【工具内部实现逻辑】

def diagnose_metric(metric_name, metric_sql_template, period_a, period_b, drill_dimensions, decomposition_formula=None):
    """
    内部执行多步归因分析:
    
    Step 1: 计算两期的总体指标值,确认变化幅度
    Step 2: (可选) 如果有分解公式,先做指标拆解
    Step 3: 对每个 drill_dimension,计算两期在该维度下的分布
    Step 4: 计算每个维度子项的"变化贡献度":
           contribution = (period_b_value - period_a_value) / total_change
    Step 5: 找出 Top 3 异常子项(贡献度最大的)
    Step 6: 整合分析结果,返回结构化报告
    """
    
    results = {
        "overview": {...},          # 总体变化
        "decomposition": {...},     # 指标拆解结果(如果有)
        "dimension_analysis": [     # 各维度下钻结果
            {
                "dimension": "品类",
                "top_contributors": [
                    {"name": "电子产品", "change": -25000, "contribution_pct": 45.2, "evidence": "..."}
                ]
            }
        ],
        "conclusion": "...",        # LLM 生成的归因结论
        "confidence": "高/中/低",   # 置信度
        "limitations": "..."        # 局限性说明
    }
    return results

【关键设计点】

1. 这个工具内部会调用多次 SQL,但对 LLM 表现为一次工具调用
2. 工具返回的是结构化分析报告,不是原始数据
3. 在工具内部,用 LLM 生成最终的"归因结论"(可以再调一次 LLM)
4. 必须输出"置信度"和"局限性",这是专业感的体现

【加在 prompts.py 中的指引】

在 AGENT_SYSTEM_PROMPT 加一段:
```
当用户问"为什么 X 变了""X 下跌的原因"这类问题时,优先使用 diagnose_metric 工具。
使用前,你需要:
1. 确认指标定义(如"用户流失"是指什么)
2. 确认对比的两个时期
3. 决定下钻哪些维度(基于业务理解,通常包括: 渠道/地区/品类/用户分群)
4. 如果指标有清晰的分解公式,提供 decomposition_formula

输出归因结论时,必须包括:
- 主要发现(Top 3 贡献因素)
- 数据证据(具体数字)
- 置信度评估
- 局限性说明(没看到的因素)
- 建议下一步动作
```

【测试场景】
用户: "2018 年 1 月销售额比 2017 年 12 月下跌了,为什么?"

预期 Agent 流程:
1. 先用 query_database 确认下跌幅度
2. 调 diagnose_metric,传入:
   - metric_name: "销售额"
   - period_a: 2017-12
   - period_b: 2018-01
   - drill_dimensions: [品类, 州, 支付方式]
3. 工具内部:计算总体变化 → 各维度下钻 → 找异常子集 → 生成结论
4. Agent 把结果用 make_chart 画对比图
5. 最后输出归因报告

【交付方式】
这个工具复杂,请分三步:
1. 先实现 diagnose_metric 的核心逻辑(SQL 生成、贡献度计算)
2. 然后接入到 Agent
3. 最后用 2-3 个真实问题测试效果
```

### 4.3 Day 21:主动洞察 + 报告生成

**📋 Prompt 模板:**

```
最后两个加分功能,做完 Week 3 就完整了。

【任务 1: 主动洞察】

修改 prompts.py 的 AGENT_SYSTEM_PROMPT,加入:
```
完成每一轮分析后,你应该主动推荐下一步可深挖的方向。
推荐格式:
"基于本轮分析,我注意到几个值得深入的方向:
[1] {方向1}: {理由}
[2] {方向2}: {理由}  
[3] {方向3}: {理由}
请告诉我你想深挖哪个,或者继续问其他问题。"

推荐时遵循:
- 优先推荐发现的异常点
- 优先推荐有业务价值的方向
- 不要超过 3 个建议
- 用编号方便用户快速选择
```

【任务 2: 报告生成工具】

新增 generate_report 工具:

{
    "type": "function",
    "function": {
        "name": "generate_report",
        "description": "把当前会话的所有分析整合成一份完整的 Markdown 报告",
        "parameters": {
            "type": "object",
            "properties": {
                "report_title": {
                    "type": "string",
                    "description": "报告标题,如 '2017 年 Q4 销售分析周报'"
                },
                "include_sections": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["背景", "核心发现", "详细分析", "归因结论", "建议", "附录"]
                    },
                    "description": "要包含的章节"
                },
                "audience": {
                    "type": "string",
                    "enum": ["management", "operation", "technical"],
                    "description": "报告受众: management(管理层,简洁) / operation(运营,可执行) / technical(技术,详细)"
                }
            },
            "required": ["report_title", "include_sections"]
        }
    }
}

实现要求:
- 工具会读取 session_state 中的所有历史分析结果
- 用 LLM 整合成 Markdown 格式
- 在 Streamlit 中用 st.markdown 显示
- 加一个"下载报告"按钮(st.download_button)

【任务 3: 优化 Agent System Prompt】

把 prompts.py 中的 AGENT_SYSTEM_PROMPT 整理成最终版,包括:
- 角色定义
- 可用工具清单
- 工作流程(简单问题/多步问题/归因问题)
- 输出风格要求
- 主动洞察规则
- 局限性说明要求

【交付方式】
最后给我一份完整的 prompts.py,我作为项目的"灵魂"文件保存。
```

**✅ Week 3 完成标志:**
- 至少能跑通 3 个完整的复杂场景
- 归因诊断能给出有理有据的结论
- 能一键生成完整分析报告
- Agent 会主动推荐下一步分析方向

---

## 五、Week 4 · 求职作品包装

不写代码,做"营销"。这是项目对求职最有杠杆的部分。

### 5.1 Day 22:部署上线

```bash
# 1. 整理 requirements.txt
pip freeze > requirements.txt

# 2. 推 GitHub
git init
git add .
git commit -m "feat: AI data analyst agent v1.0"
git remote add origin https://github.com/{你的用户名}/ai-data-agent.git
git push -u origin main

# 3. 在 Streamlit Community Cloud 一键部署
# 访问 share.streamlit.io,绑定 GitHub 即可
# 注意把 DEEPSEEK_API_KEY 加到 Streamlit Secrets
```

### 5.2 Day 23-24:GitHub README

README 必须包含:
1. **项目简介(2-3 句)**:解决什么问题、给谁用
2. **在线 Demo 链接**:让面试官能直接体验
3. **架构图**:把本文档第 1 节的架构图截图放进去
4. **核心场景演示**:3 个 GIF 动图(用 [Kap](https://getkap.co/) 录制)
5. **技术选型说明**:为什么选 DeepSeek、为什么不用 LangChain、为什么用 DuckDB
6. **未来改进方向**:展示你有产品视角

### 5.3 Day 25-26:技术复盘文章

发到掘金 + 知乎 + 小红书。标题参考:
- "数据分析师如何用 AI 重构自己的工作流:一个 Agent 项目实践"
- "为什么我没用 LangChain,从零写了一个数据分析 Agent"
- "3.5 年数据分析师的 AI 转型实验"

**文章结构:**
1. 我为什么做这个(业务痛点)
2. 我怎么设计的(架构图 + 关键决策)
3. 我踩过的坑(3-5 个具体的)
4. 效果展示(实际 demo)
5. 局限和未来

### 5.4 Day 27:录 Demo 视频

3-5 分钟,结构:
- 0:00-0:30 项目背景:解决什么问题
- 0:30-2:30 演示 3 个核心场景(基础查询 / 多步分析 / 归因诊断)
- 2:30-3:30 技术架构 1 分钟讲清
- 3:30-4:30 业务价值 + 反思
- 4:30-5:00 总结 + 联系方式

### 5.5 Day 28:简历更新 + 面试准备

**简历项目描述模板:**

```
AI 数据分析 Agent | 个人项目 | 2026.X
个人开发的数据分析师 AI 助手,能通过自然语言完成数据查询、可视化、归因分析全流程。

技术栈: Python | Streamlit | DeepSeek API | DuckDB | Plotly
GitHub: github.com/xxx | Demo: xxx.streamlit.app

核心亮点:
• 设计 Agent 架构,通过 Function Calling 实现工具调用 + 多步规划 + 多轮记忆
• 用 DuckDB 作为统一查询层,支持 Excel / CSV / 数据库的统一 SQL 访问
• 实现归因诊断工具,自动完成指标拆解 + 维度下钻 + 贡献度量化
• 项目已部署上线,文章发布在掘金/知乎,获得 XXX 阅读
```

**面试话术准备 5 个问题:**

1. 这个项目的设计思路是什么?
2. 为什么选 DeepSeek?为什么不用 LangChain?
3. 如何让 Agent 能处理复杂多步问题?
4. 归因诊断这个工具内部是怎么工作的?
5. 这个 Agent 的局限性是什么?如果在公司落地,你会如何改进?

每个问题准备 1-2 分钟的回答,**对着镜子练 3 遍**。

---

## 六、附录 A · Agent System Prompt 模板

把这段保存为 `src/prompts.py` 中的 `AGENT_SYSTEM_PROMPT`:

```python
AGENT_SYSTEM_PROMPT = """
你是一个专业的数据分析师 AI Agent,帮助用户完成数据查询、可视化和深度分析。

## 你的能力
你可以调用以下工具:
1. query_database: 执行 SQL 查询
2. make_chart: 生成 Plotly 交互式图表
3. analyze_dataframe: 做基础统计分析
4. diagnose_metric: 多维度归因诊断
5. generate_report: 生成 Markdown 报告

## 工作原则

### 简单问题
对于明确的查询(如"2017年总销售额"),直接调 query_database,然后视情况调 make_chart。

### 复杂多步问题
对于需要多步骤的问题,你必须:
1. 先用一段话说明你的"分析计划"(不调用工具,只输出文本)
2. 然后逐步调用工具执行
3. 每一步执行后,简要说明这一步的发现
4. 全部完成后,综合所有发现给出最终结论

### 归因诊断问题
当用户问"为什么 X 变了""X 下跌的原因"时,优先使用 diagnose_metric 工具。
使用前先确认:
- 指标定义(询问用户或用默认)
- 对比的两个时期
- 要下钻的维度(基于业务理解选 3-5 个)

### 模糊问题处理
如果用户问题模糊,先澄清再执行。不要凭猜测生成 SQL。
例: 用户说"近期销售如何?",你应该问:"请确认'近期'是指最近 7 天、30 天,还是本月?"

## 输出风格

### 数据展示
- 数字要带单位
- 大数字用千分位或"万/亿"格式化
- 关键发现要量化(不要只说"上升明显",要说"上升 23%")

### 图表选择
- 时间序列优先 line
- 分类对比 ≤8 类用 bar,>8 类或名长用 barh  
- 占比 ≤5 类用 pie/donut
- 不同量级双指标用 combo
- 不确定时优先 bar 或 table

### 业务语言
- 统计术语首次出现时给中文通俗解释
- 数字结论要结合业务含义
- 不过度解读,数据不足时明确告知局限

## 主动洞察

每完成一轮分析,你必须主动推荐下一步:
"基于本轮分析,我注意到几个值得深入的方向:
[1] {方向1}: {理由}
[2] {方向2}: {理由}
[3] {方向3}: {理由}
请告诉我你想深挖哪个,或者继续问其他问题。"

规则:
- 优先推荐发现的异常点
- 优先推荐有业务价值的方向
- 最多 3 个建议
- 用编号方便用户选择

## 上下文使用

充分利用对话历史:
- 用户说"那""这个"等代词时,正确指向之前的内容
- 用户定义过的术语(如"活跃用户=最近30天有下单")要沿用
- 已查过的数据不要重复查询,直接引用

## 边界与诚实

- 数据没说明的不要编(如缺渠道字段时不要凭空说"渠道分析")
- 归因结论要标注置信度(高/中/低)和局限性
- 如果用户的问题超出能力范围,坦诚告知

## 安全约束

- 只生成 SELECT 查询,绝不生成 INSERT/UPDATE/DELETE/DROP
- 涉及敏感字段(手机号、邮箱)时自动脱敏显示
- 不要执行没有 WHERE 条件的全表扫描(除非用户明确要)
"""
```

---

## 七、附录 B · 调试与优化建议

### 常见问题排查

**Q: DeepSeek 返回的 tool_calls 为空怎么办?**
A: 几种可能:
1. 用户问题不需要工具(纯聊天)→ 正常
2. tools 描述写得不够清晰 → 优化 description
3. temperature 太低 → 调到 0.3-0.5
4. system prompt 没强调要用工具 → 加一句"如果需要查询数据,必须调用工具,不要凭记忆回答"

**Q: SQL 经常生成错怎么办?**
A: 检查:
1. schema 是否完整传给了 LLM(包括字段类型、表关系)
2. 是否提供了 few-shot 示例(在 prompt 里加 1-2 个示例 SQL)
3. 复杂 JOIN 时,是否在 schema 注释里说明了关联关系

**Q: 多轮对话上下文丢失?**
A: 检查 messages 数组是否完整传递,特别是 tool message 不能截断 tool_call_id。

**Q: Agent 死循环怎么办?**
A: agent.py 主循环必须有 max_iterations 限制(建议 10),超过就强制退出。

### 性能优化

1. **对话历史压缩**:超过一定长度时,用 LLM 总结早期对话
2. **SQL 结果缓存**:相同 SQL 不重复执行,缓存到 session_state
3. **流式输出**:用 stream=True 让回答边生成边显示,提升体验
4. **并行工具调用**:DeepSeek 支持 parallel tool calls,可以同时调多个 query_database

---

## 八、检查清单

完成项目前,确认以下事项都做完:

### 功能完整性
- [ ] 能上传 Excel/CSV 并查询
- [ ] 能查询预置 Olist 数据集
- [ ] 至少 7 种图表类型可用
- [ ] 能处理多步分析问题
- [ ] 归因诊断工具能跑通
- [ ] 能生成完整 Markdown 报告
- [ ] 多轮对话上下文连贯
- [ ] 错误能友好提示

### 工程质量
- [ ] 代码有详细注释
- [ ] 关键函数有 docstring
- [ ] requirements.txt 完整
- [ ] .env.example 文件存在(不含真实 key)
- [ ] .gitignore 排除了敏感文件

### 求职准备
- [ ] 项目部署上线,有公开 URL
- [ ] GitHub README 完整(架构图 + GIF + 说明)
- [ ] 至少 1 篇技术复盘文章发布
- [ ] 3-5 分钟 demo 视频录制完成
- [ ] 简历项目描述写好
- [ ] 5 个常见面试问题准备好

---

完成所有这些,你就有了一个完整的、能讲能演示的 AI 数据分析 Agent 求职作品。

祝你拿到心仪的 offer 🎯
