# AI 数据分析 Agent · 完整开发手册 v3

> 适用对象:有 SQL + Pandas 基础,使用 Claude Code 辅助开发的数据分析师
> LLM 选型:DeepSeek-V3 (deepseek-chat)
> 预计工期:4 周(每周约 10-15 小时)

---

## 修订说明(v1 → v2 → v3)

> v2 修订修复了 5 个结构性问题,对应章节已标注 `[v2 修订]`。
> v3 在 v2 基础上新增**词云图、漏斗图、气泡图**三种图表类型,对应章节已标注 `[v3 新增]`。

| # | 问题 / 新增 | 影响 | 位置 |
|---|---|---|---|
| 1 | `last_result` 跨轮污染导致图表画错数据 | 🔴 严重 Bug | 3.2 节 |
| 2 | SQL 确认按钮打断 Agent 多步流 | 🟠 体验矛盾 | 2.4 节 + 3.2 节 |
| 3 | 归因工具复杂度低估,时间和实现方案不足 | 🟠 进度风险 | 4.2 节 |
| 4 | 图表类型无硬校验,完全依赖 LLM 自律 | 🟡 质量隐患 | 4.1 节 |
| 5 | 报告只有 Markdown,无法直接发给领导/同事 | 🟡 实用性缺口 | 4.3 节 |
| 6 | **[v3]** 新增词云图(wordcloud)实现与校验 | 🟢 能力扩展 | 4.1 节 |
| 7 | **[v3]** 新增漏斗图(funnel)实现与校验 | 🟢 能力扩展 | 4.1 节 |
| 8 | **[v3]** 新增气泡图(bubble)实现与校验 | 🟢 能力扩展 | 4.1 节 |
| 9 | **[v3]** Day 22 报告新增 PDF 导出(含图表嵌入) | 🟢 能力扩展 | 4.3 节 |

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
| 可视化(结构化) | Plotly | 交互式图表(漏斗图、气泡图等) |
| 可视化(文本) | wordcloud + matplotlib | 词云图渲染(v3 新增) |
| 报告导出(Word) | python-docx | Word 格式导出(v2 新增) |
| 报告导出(PDF) | weasyprint + markdown + kaleido | PDF 生成:MD→HTML→PDF + 图表嵌入(v3 新增) |
| 部署 | Streamlit Community Cloud | 免费 |

### 1.3 环境准备

```bash
# 核心依赖(Week 1-4,与 v2 相同)
pip install streamlit duckdb pandas plotly openai python-dotenv openpyxl python-docx

# v3 新增:词云图依赖
pip install wordcloud matplotlib
# 如果你的数据包含中文文本,还需要:
pip install jieba

# v3 新增:PDF 报告依赖
pip install weasyprint markdown kaleido
```

> **关于 PDF 依赖库的说明:**
>
> - `markdown`:把 Markdown 文本转换为 HTML 字符串
> - `weasyprint`:把 HTML + CSS 渲染成 PDF(支持中文、表格、图片嵌入)
> - `kaleido`:Plotly 官方的图表静态导出引擎,负责把 Plotly 图表转成 PNG 字节流再嵌入 PDF
>
> **⚠️ Windows 安装 weasyprint 注意事项:**
> weasyprint 在 Windows 上依赖 GTK 运行时,安装比 Linux/Mac 复杂。
> 推荐三种解决方式(任选其一):
> 1. 用 **WSL2**(Windows Subsystem for Linux),在 Linux 环境下开发(最省事)
> 2. 按 [weasyprint 官方 Windows 文档](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows) 安装 GTK
> 3. 用 **`fpdf2`** 作为替代方案(不依赖 GTK,但不支持从 HTML 渲染,格式较简单):
>    ```bash
>    pip install fpdf2
>    ```
>    fpdf2 替代方案的实现会在附录 D 中单独说明。

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
├── assets/
│   └── fonts/               # [v3 新增] 中文字体文件(词云用)
│       └── SimHei.ttf       # 放这里即可,代码自动检测
├── src/
│   ├── app.py               # Streamlit 主程序
│   ├── agent.py             # Agent 核心:LLM 调用 + 工具循环
│   ├── tools.py             # 工具定义(SQL/图表/分析/归因/报告)
│   ├── data_source.py       # 数据源抽象层
│   ├── prompts.py           # System Prompt 模板
│   ├── validators.py        # [v2 新增] 图表校验 + 输出质量规则
│   ├── chart_utils.py       # [v3 新增] 词云图渲染工具函数
│   ├── report_builder.py    # [v3 新增] Word + PDF 报告构建模块
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

### 4.1 Day 15-17:智能图表系统 [v2 修订 + v3 新增]

> ⚠️ **v2 修订说明(对应问题 4)**
>
> v1 中图表类型完全由 LLM 自主决定,没有任何硬校验。
> 问题在于 LLM 会犯明显的错误,比如用饼图展示 20 个品类。
>
> **修复方案:** 新增 `src/validators.py`,把常识性规则用代码硬编码,
> LLM 决策的结果必须经过校验层才能执行。这层校验不是"推翻 LLM",
> 而是"纠正 LLM 的低级失误"。

> 🟢 **v3 新增说明**
>
> 在 v2 的 10 种图表基础上新增 3 种:
> - **词云图(wordcloud)**: 文本频率可视化,需要 `wordcloud + matplotlib` 库
> - **漏斗图(funnel)**: 流程转化率分析,Plotly 原生支持
> - **气泡图(bubble)**: 三维变量同时展示,Plotly 原生支持
>
> 三种图表均有对应的校验规则和完整的 Prompt 模板。

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

    # [v3 新增] 规则 5 - 漏斗图阶段数检查:
      if chart_type == "funnel":
          if len(df) < 2:
              return "bar", "漏斗图至少需要 2 个阶段,已自动切换为柱状图"
          if len(df) > 10:
              return "barh", f"漏斗图阶段数({len(df)})过多(建议≤10),已自动切换为横向条形图"
    
    # [v3 新增] 规则 6 - 气泡图三列数值检查:
      if chart_type == "bubble":
          # x_col 和 y_col 必须是数值
          if not pd.api.types.is_numeric_dtype(df[x_col]):
              return "scatter", "气泡图 X 轴必须是数值字段,已降级为散点图"
          if not pd.api.types.is_numeric_dtype(df[y_col]):
              return "scatter", "气泡图 Y 轴必须是数值字段,已降级为散点图"
          # size_col 由调用方在 bubble_options 里校验
    
    # [v3 新增] 规则 7 - 词云图字段检查(在 make_chart 调用前由 chart_utils 校验):
      if chart_type == "wordcloud":
          # 词云的校验在 chart_utils.validate_wordcloud_input() 中进行
          # 这里只做基本检查:数据不能为空
          if len(df) == 0:
              return "table", "数据为空,无法生成词云"
      
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
                             "heatmap","area","combo","table",
                             "wordcloud","funnel","bubble"],
                    "description": "图表类型。选择规则:\n- line: 时间序列趋势(X轴必须是时间)\n- bar: 分类对比(类别≤8个)\n- barh: 横向条形图(类别名长 或 >8个)\n- pie/donut: 构成占比(类别≤5个,总和有意义)\n- scatter: 两个连续变量相关性(X和Y都必须是数值)\n- heatmap: 二维交叉分析\n- area: 累积量或占比变化\n- combo: 双轴图(柱+线,不同单位)\n- table: 精确数值查阅\n- wordcloud: 文本词频可视化(需要文本字段或词频统计)\n- funnel: 漏斗图,展示流程转化(各阶段数值必须递减)\n- bubble: 气泡图,同时展示三个数值维度(X/Y/气泡大小)\n注意: 代码层会对不合适的类型自动降级,但请尽量选对。"
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
                },
                "wordcloud_options": {
                    "type": "object",
                    "description": "[v3 新增] 词云图专用参数,仅当 chart_type='wordcloud' 时填写",
                    "properties": {
                        "text_col": {
                            "type": "string",
                            "description": "原始文本字段名(如 review_comment_message)。与 freq_col 二选一填写。"
                        },
                        "word_col": {
                            "type": "string",
                            "description": "词语字段名(已分词时填写,如 'keyword')。与 text_col 二选一。"
                        },
                        "freq_col": {
                            "type": "string",
                            "description": "词频字段名(已有频次统计时填写,如 'count')。与 text_col 二选一。"
                        },
                        "colormap": {
                            "type": "string",
                            "enum": ["viridis","plasma","RdYlBu_r","Reds","Blues","Greens","Set2"],
                            "description": "颜色方案。负面情绪用 Reds,正面用 Greens,中性用 viridis",
                            "default": "viridis"
                        },
                        "max_words": {
                            "type": "integer",
                            "description": "最多显示的词数,默认 80",
                            "default": 80
                        },
                        "language": {
                            "type": "string",
                            "enum": ["zh","en","pt","auto"],
                            "description": "文本语言。zh=中文(使用jieba分词),pt=葡萄牙语,auto=自动检测",
                            "default": "auto"
                        }
                    }
                },
                "funnel_options": {
                    "type": "object",
                    "description": "[v3 新增] 漏斗图专用参数,仅当 chart_type='funnel' 时填写",
                    "properties": {
                        "stage_col": {
                            "type": "string",
                            "description": "阶段名称字段(如 'order_status' / '渠道步骤'),即漏斗的各层标签"
                        },
                        "value_col": {
                            "type": "string",
                            "description": "各阶段对应的数值字段(如 'count'),数值应从大到小排列"
                        },
                        "show_pct": {
                            "type": "boolean",
                            "description": "是否在每层显示转化率百分比,默认 true",
                            "default": True
                        },
                        "orientation": {
                            "type": "string",
                            "enum": ["vertical","horizontal"],
                            "description": "漏斗方向。vertical=竖向(常见),horizontal=横向(阶段名较长时用)",
                            "default": "vertical"
                        }
                    }
                },
                "bubble_options": {
                    "type": "object",
                    "description": "[v3 新增] 气泡图专用参数,仅当 chart_type='bubble' 时填写",
                    "properties": {
                        "size_col": {
                            "type": "string",
                            "description": "控制气泡大小的字段(必须是数值,如 'order_count' / 'gmv')"
                        },
                        "label_col": {
                            "type": "string",
                            "description": "气泡标签字段(悬停时显示,如 'product_category')"
                        },
                        "size_max": {
                            "type": "integer",
                            "description": "最大气泡的像素尺寸,默认 60",
                            "default": 60
                        },
                        "color_col": {
                            "type": "string",
                            "description": "气泡颜色分类字段(可选),用于区分不同组别"
                        }
                    }
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

---

### 4.1.1 [v3 新增] 词云图(wordcloud)实现详解

#### 适用场景

| 场景 | 示例问题 |
|---|---|
| 用户评论关键词可视化 | "把差评的高频词做成词云" |
| 品类描述词频分析 | "显示各商品描述里最常出现的词" |
| 文本数据快速探索 | "用词云展示本月客服记录的主要关键词" |

#### 为什么词云不能用 Plotly

Plotly 是专为结构化数值数据设计的交互式图表库,没有词频布局算法。词云需要专门的排版引擎(`wordcloud` 库)根据词频计算每个词的大小和位置,最终输出为静态图片格式,再用 `matplotlib` + `st.image` 渲染到页面。这是一个不同于其他图表的渲染路径。

#### 数据要求

词云接受两种输入格式:

| 输入格式 | 示例数据 | 说明 |
|---|---|---|
| 原始文本列 | `review_comment_message` 列 | 代码内部自动分词 + 统计频次 |
| 已统计词频 | `keyword` 列 + `count` 列 | 直接用于渲染,跳过分词步骤 |

**基于 Olist 的典型 SQL:**

```sql
-- 格式一:原始文本(让代码自动分词)
SELECT review_comment_message
FROM order_reviews
WHERE review_score <= 2
  AND review_comment_message IS NOT NULL
  AND LENGTH(review_comment_message) > 5;

-- 格式二:预先统计词频(DuckDB 不支持直接分词,需 Pandas 处理后再用)
-- 先查原始文本,在 Python 里用 jieba/空格切割统计频次,得到 {word: count} 字典
```

#### 实现方案:新建 `src/chart_utils.py`

词云的渲染逻辑独立放在 `chart_utils.py`,不混入 `tools.py`,原因是它依赖的库(`wordcloud`、`matplotlib`)与其他图表不同,单独管理便于测试和维护。

**📋 Prompt 模板(发给 Claude Code):**

```
基于已有的 tools.py 和 validators.py,现在要新增词云图能力。
词云图使用独立的渲染库,需要新建一个工具模块。

【技术栈】
- wordcloud: 词频布局算法
- matplotlib: 图片渲染(输出 PNG bytes)
- streamlit: st.image 显示 + st.download_button 下载
- jieba: 中文分词(仅当数据为中文时)
- Pandas: 文本预处理

【任务一:新建 src/chart_utils.py】

实现以下两个函数:

def get_font_path() -> str | None:
    """
    自动检测可用的中文字体路径,按优先级:
    1. assets/fonts/SimHei.ttf(项目内置)
    2. 系统字体(Windows: simhei.ttf / Mac: STHeiti Light / Linux: wqy-zenhei)
    3. 返回 None,降级为英文字体(中文显示为方块,届时打印警告)
    """
    import os, platform
    project_font = os.path.join(
        os.path.dirname(__file__), '..', 'assets', 'fonts', 'SimHei.ttf'
    )
    if os.path.exists(project_font):
        return os.path.abspath(project_font)
    
    system_fonts = {
        'Windows': ['C:/Windows/Fonts/simhei.ttf', 'C:/Windows/Fonts/msyh.ttc'],
        'Darwin':  ['/System/Library/Fonts/STHeiti Light.ttc'],
        'Linux':   ['/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
                    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
    }
    for path in system_fonts.get(platform.system(), []):
        if os.path.exists(path): return path
    print("⚠️ 未找到中文字体,词云中文可能显示为方块。请将 SimHei.ttf 放入 assets/fonts/")
    return None

def render_wordcloud(
    df: pd.DataFrame,
    text_col: str | None,        # 原始文本列名,与 word_col+freq_col 二选一
    word_col: str | None,        # 词语列名(已分词场景)
    freq_col: str | None,        # 词频列名(已分词场景)
    title: str,
    colormap: str = "viridis",
    max_words: int = 80,
    language: str = "auto"
) -> bytes:
    """
    渲染词云图,返回 PNG bytes。
    不依赖 Streamlit(方便单元测试)。
    
    内部逻辑:
    1. 构建词频字典:
       - 如果提供 text_col: 用 jieba(中文)/split(英文/葡萄牙语) 分词后统计
       - 如果提供 word_col + freq_col: 直接构建 {word: freq} 字典
    
    2. 过滤停用词(中文常见停用词列表内置,英文/葡语跳过)
    
    3. 生成词云:
       wc = WordCloud(
           width=900, height=450,
           background_color='white',
           colormap=colormap,
           max_words=max_words,
           font_path=get_font_path(),
           prefer_horizontal=0.85,
           collocations=False          # 避免词组重复
       ).generate_from_frequencies(freq_dict)
    
    4. 用 matplotlib 渲染:
       fig, ax = plt.subplots(figsize=(12, 6))
       ax.imshow(wc, interpolation='bilinear')
       ax.axis('off')
       ax.set_title(title, fontsize=16, fontproperties=font_prop)
    
    5. 输出为 PNG bytes:
       buf = BytesIO()
       fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
       plt.close(fig)
       return buf.getvalue()
    """
    pass  # 请实现

【任务二:在 tools.py 的 make_chart 函数中加入词云分支】

在 make_chart 的图表类型分发逻辑里加入:

elif chart_type == "wordcloud":
    # 从 wordcloud_options 里取参数
    wc_opts = kwargs.get('wordcloud_options', {})
    png_bytes = chart_utils.render_wordcloud(
        df=df,
        text_col=wc_opts.get('text_col'),
        word_col=wc_opts.get('word_col'),
        freq_col=wc_opts.get('freq_col'),
        title=title,
        colormap=wc_opts.get('colormap', 'viridis'),
        max_words=wc_opts.get('max_words', 80),
        language=wc_opts.get('language', 'auto')
    )
    # 显示词云
    st.image(png_bytes, caption=title, use_column_width=True)
    # 下载按钮
    st.download_button(
        label="⬇️ 下载词云图 (PNG)",
        data=png_bytes,
        file_name=f"{title}.png",
        mime="image/png"
    )
    # 显示 insight
    st.info(f"💡 {insight}")

【任务三:在 validators.py 中加入词云校验】

新增函数 validate_wordcloud_input(df, wc_opts):
- 检查 text_col 或 (word_col + freq_col) 至少提供一组
- text_col 存在但所有值为空: 返回错误"文本列全为空值,无法生成词云"
- 词频统计后有效词数 < 5: 返回警告"有效词数过少(< 5),词云效果可能较差"
- freq_col 指定了但不是数值类型: 返回错误"词频列必须是数值类型"

【约束】
- render_wordcloud 函数不能依赖 streamlit,必须是纯 Python 函数
- 字体找不到时不能抛出异常,必须降级并打印警告
- 中文数据: language='zh' 时使用 jieba.cut;其他语言用 str.split() 简单分词
- max_words 上限设为 200,超过时自动截断并打印提示

【交付方式】
1. 先写 chart_utils.py 的 get_font_path 和 render_wordcloud(含注释)
2. 然后更新 tools.py 加入词云分支
3. 然后更新 validators.py 加入词云校验
4. 写一个独立测试脚本 test_wordcloud.py:
   用一个包含 10 个词 + 词频的假数据测试 render_wordcloud 能否返回 bytes
5. 告诉我:如果用户上传的是中文数据但没装 jieba,代码会怎么处理?
```

**✅ 词云图完成标志:**
- 用户说"把差评关键词做成词云",Agent 能调 `make_chart(chart_type='wordcloud', ...)`
- 页面显示词云图片
- 有"下载 PNG"按钮
- 中文词云在 Windows/Mac/Linux 三个平台都能正确显示

**基于 Olist 的测试场景:**

```
用户: "查出评分低于 2 分的评论,把高频词做成词云"

Agent 执行:
Step 1: query_database
  SQL: SELECT review_comment_message FROM order_reviews
       WHERE review_score <= 2 AND review_comment_message IS NOT NULL
  intent: "差评文本"

Step 2: make_chart
  chart_type: "wordcloud"
  result_key: "差评文本"
  title: "Olist 差评高频词云"
  wordcloud_options: {
    "text_col": "review_comment_message",
    "colormap": "Reds",
    "max_words": 80,
    "language": "pt"
  }
```

---

### 4.1.2 [v3 新增] 漏斗图(funnel)实现详解

#### 适用场景

| 场景 | 示例问题 |
|---|---|
| 订单状态流转分析 | "各阶段的订单数量是多少,哪里流失最严重?" |
| 用户行为路径分析 | "从浏览到购买各阶段的转化情况" |
| 流程效率分析 | "订单从创建到交付的各环节通过率" |

漏斗图的核心价值是展示**从起点到终点的逐层损耗**,适合任何"先多后少"的流程数据。

#### 数据要求

| 字段 | 类型 | 说明 |
|---|---|---|
| `stage_col` | 字符串 | 阶段名称,如"已创建/已批准/已发货/已送达" |
| `value_col` | 数值 | 各阶段数量,**必须从大到小排列**(代码会自动排序) |

**基于 Olist 的典型 SQL:**

```sql
-- 订单状态漏斗:各状态的订单数
SELECT
    CASE order_status
        WHEN 'created'    THEN '1.已创建'
        WHEN 'approved'   THEN '2.已批准'
        WHEN 'processing' THEN '3.处理中'
        WHEN 'shipped'    THEN '4.已发货'
        WHEN 'delivered'  THEN '5.已送达'
        WHEN 'canceled'   THEN '取消(不计入漏斗)'
    END AS stage,
    COUNT(*) AS order_count
FROM orders
WHERE order_status NOT IN ('canceled', 'unavailable')
GROUP BY order_status
ORDER BY order_count DESC;
```

#### 实现方案(Plotly 原生)

漏斗图是 Plotly 的原生图表类型,无需额外依赖:

```python
import plotly.express as px
import plotly.graph_objects as go

# 方式一:px.funnel(简洁,推荐)
fig = px.funnel(
    df,
    x=value_col,        # 数值
    y=stage_col,        # 阶段名称
    title=title,
    color_discrete_sequence=COLOR_PALETTE
)

# 方式二:go.Funnel(更多自定义控制)
fig = go.Figure(go.Funnel(
    y=df[stage_col],    # 阶段(Y轴=垂直方向的阶段名)
    x=df[value_col],    # 数值
    textposition="inside",
    textinfo="value+percent previous",  # 显示数值和相对上一步的转化率
    marker={"color": COLOR_PALETTE[:len(df)]}
))
```

**📋 Prompt 模板(发给 Claude Code):**

```
现在要在 make_chart 中加入漏斗图(funnel)的实现。

【技术栈】
- plotly.express (px.funnel) 或 plotly.graph_objects (go.Funnel)
- 无需额外依赖,Plotly 原生支持

【任务一:在 tools.py 的 make_chart 中加入漏斗图分支】

实现要求:
elif chart_type == "funnel":
    funnel_opts = kwargs.get('funnel_options', {})
    stage_col = funnel_opts.get('stage_col', x_col)
    value_col_f = funnel_opts.get('value_col', y_col)
    show_pct = funnel_opts.get('show_pct', True)
    orientation = funnel_opts.get('orientation', 'vertical')
    
    # 1. 数据预处理:按 value_col 从大到小排序(漏斗必须递减)
    df_funnel = df[[stage_col, value_col_f]].copy()
    df_funnel = df_funnel.sort_values(value_col_f, ascending=False)
    
    # 2. 计算转化率:每层相对第一层(漏斗顶部)的百分比
    total = df_funnel[value_col_f].iloc[0]
    df_funnel['conversion_rate'] = (df_funnel[value_col_f] / total * 100).round(1)
    df_funnel['step_rate'] = df_funnel[value_col_f].pct_change().fillna(0) * 100
    
    # 3. 构建 text_info:显示数值 + 对顶层的转化率
    text_labels = [
        f"{row[value_col_f]:,}<br>{row['conversion_rate']}%"
        for _, row in df_funnel.iterrows()
    ]
    
    # 4. 用 go.Funnel 实现(比 px.funnel 更灵活)
    fig = go.Figure(go.Funnel(
        y=df_funnel[stage_col],
        x=df_funnel[value_col_f],
        text=text_labels,
        textposition="inside",
        textinfo="text",
        connector={"line": {"color": "royalblue", "width": 2}}
    ))
    
    fig.update_layout(
        title=title,
        funnelmode="stack" if orientation == "horizontal" else "overlay"
    )
    
    # 5. 如果 show_pct=True,在每段之间加转化率标注
    if show_pct:
        for i in range(1, len(df_funnel)):
            step_loss = df_funnel[value_col_f].iloc[i-1] - df_funnel[value_col_f].iloc[i]
            step_pct = df_funnel['step_rate'].iloc[i]
            # 在图上用 annotation 标注流失量和流失率
            fig.add_annotation(
                x=0.5, y=i - 0.5,
                text=f"▼ 流失 {step_loss:,} ({abs(step_pct):.1f}%)",
                showarrow=False,
                font=dict(size=11, color="gray"),
                xref="paper"
            )
    
    st.plotly_chart(fig, use_container_width=True)
    st.info(f"💡 {insight}")
    
    # 显示原始数据表(包含转化率)
    with st.expander("查看转化率明细"):
        st.dataframe(df_funnel[[stage_col, value_col_f, 'conversion_rate']].rename(
            columns={stage_col: '阶段', value_col_f: '数量', 'conversion_rate': '转化率(%)'}
        ))

【任务二:在 validators.py 中加入漏斗图校验】

在 validate_chart_type 中加入:
- len(df) < 2: 降级为 bar + 警告"漏斗图至少需要 2 个阶段"
- len(df) > 10: 降级为 barh + 警告"阶段数过多,建议合并或使用条形图"
- value_col 的值不是单调递减:不降级,但显示提示
  "⚠️ 漏斗图数据已按数值从大到小重新排序"

【约束】
- 数据排序必须在渲染前自动完成,不需要用户手动保证顺序
- 转化率计算基准统一为漏斗顶层(第一层),不是上一层
- 流失标注用 go.Figure annotation 实现,不要改变图表主体结构
- 横向漏斗(orientation='horizontal')时,标注位置要对应调整

【测试用例】
基于 Olist 数据测试:
"查看订单各状态的数量,生成漏斗图"
→ 预期: 已创建 > 已批准 > 已发货 > 已送达,每层显示转化率

【交付方式】
1. 先写漏斗图分支的完整代码
2. 然后更新 validators.py
3. 告诉我:如果数据里有 NULL 值的 stage_col 记录,代码会怎么处理?
```

**✅ 漏斗图完成标志:**
- 数据自动按数值降序排列
- 每层显示数量 + 对顶层的转化率
- 层间显示流失量和流失率
- 有"查看转化率明细"折叠表格
- 阶段数校验生效(< 2 或 > 10 自动降级)

**基于 Olist 的测试场景:**

```
用户: "订单从创建到交付各阶段分别有多少,哪个环节流失最多?"

Agent 执行:
Step 1: query_database
  SQL: SELECT order_status, COUNT(*) as order_count FROM orders
       WHERE order_status NOT IN ('canceled','unavailable')
       GROUP BY order_status
  intent: "订单状态分布"

Step 2: make_chart
  chart_type: "funnel"
  result_key: "订单状态分布"
  title: "Olist 订单状态转化漏斗"
  funnel_options: {
    "stage_col": "order_status",
    "value_col": "order_count",
    "show_pct": true
  }
  insight: "从已创建到已送达,整体转化率为 XX%,最大流失发生在 XX 阶段"
```

---

### 4.1.3 [v3 新增] 气泡图(bubble)实现详解

#### 适用场景

| 场景 | 示例问题 |
|---|---|
| 品类三维对比 | "各品类的平均价格、销量、评分三者关系" |
| 卖家绩效分析 | "各卖家的订单数、客单价、好评率分布" |
| 地区综合分析 | "各州的订单量、GMV、配送时长的关系" |

气泡图的核心是**用气泡大小引入第三个维度**,使得一张图能同时展示三个数值变量之间的关系,避免需要三张独立图表。

#### 数据要求

| 参数 | 字段类型 | 说明 |
|---|---|---|
| `x_col` | 数值 | X 轴(如平均价格) |
| `y_col` | 数值 | Y 轴(如平均评分) |
| `size_col` | 数值,正数 | 气泡大小(如销售量) |
| `label_col` | 字符串(可选) | 气泡标签(悬停时显示品类名) |
| `color_col` | 字符串(可选) | 颜色分组(如按地区分色) |

**基于 Olist 的典型 SQL:**

```sql
-- 各品类:平均价格 × 平均评分 × 订单量(气泡大小)
SELECT
    p.product_category_name                           AS category,
    AVG(oi.price)                                     AS avg_price,
    AVG(r.review_score)                               AS avg_score,
    COUNT(DISTINCT o.order_id)                        AS order_count,
    SUM(oi.price)                                     AS total_gmv
FROM orders o
JOIN order_items oi    ON o.order_id  = oi.order_id
JOIN products p        ON oi.product_id = p.product_id
JOIN order_reviews r   ON o.order_id  = r.order_id
WHERE p.product_category_name IS NOT NULL
GROUP BY p.product_category_name
HAVING COUNT(DISTINCT o.order_id) > 50    -- 过滤样本量过少的品类
ORDER BY order_count DESC
LIMIT 30;
```

#### 实现方案(Plotly 原生)

气泡图是散点图的扩展,用 `px.scatter` 的 `size` 参数实现:

```python
import plotly.express as px

fig = px.scatter(
    df,
    x=x_col,
    y=y_col,
    size=size_col,          # 气泡大小
    color=color_col,        # 气泡颜色分组(可选)
    hover_name=label_col,   # 悬停显示的标签
    hover_data={...},       # 悬停显示的额外信息
    size_max=60,            # 最大气泡尺寸(像素)
    title=title
)
```

**📋 Prompt 模板(发给 Claude Code):**

```
现在要在 make_chart 中加入气泡图(bubble)的实现。

【技术栈】
- plotly.express.scatter(size 参数实现气泡)
- 无需额外依赖

【任务一:在 tools.py 的 make_chart 中加入气泡图分支】

实现要求:
elif chart_type == "bubble":
    bubble_opts = kwargs.get('bubble_options', {})
    size_col   = bubble_opts.get('size_col')
    label_col  = bubble_opts.get('label_col')
    size_max   = bubble_opts.get('size_max', 60)
    color_col_b = bubble_opts.get('color_col', color_col)
    
    # 1. 参数校验
    if not size_col:
        st.error("气泡图需要指定 bubble_options.size_col(气泡大小字段)")
        return
    if size_col not in df.columns:
        st.error(f"字段 '{size_col}' 不存在,可用字段: {list(df.columns)}")
        return
    
    # 2. 数值校验:size_col 必须全为正数
    if df[size_col].min() <= 0:
        # 对负数/零值做偏移处理,不要直接报错
        offset = abs(df[size_col].min()) + 1
        df = df.copy()
        df[size_col] = df[size_col] + offset
        st.warning(f"⚠️ '{size_col}' 包含非正数值,已自动偏移 {offset} 以正常显示气泡")
    
    # 3. 构建 hover_data:悬停时显示所有相关字段
    hover_data = {
        x_col: ':.2f',
        y_col: ':.2f',
        size_col: ':,'
    }
    
    # 4. 绘图
    fig = px.scatter(
        df,
        x=x_col,
        y=y_col,
        size=size_col,
        color=color_col_b if color_col_b and color_col_b in df.columns else None,
        hover_name=label_col if label_col and label_col in df.columns else None,
        hover_data=hover_data,
        size_max=size_max,
        title=title,
        labels={
            x_col: x_axis_label,
            y_col: y_axis_label,
            size_col: f"气泡大小({size_col})"
        },
        color_discrete_sequence=COLOR_PALETTE
    )
    
    # 5. 增加参考线(中位数参考线)
    median_x = df[x_col].median()
    median_y = df[y_col].median()
    fig.add_vline(x=median_x, line_dash="dash", line_color="gray",
                  annotation_text=f"中位数 {median_x:.1f}", annotation_position="top right")
    fig.add_hline(y=median_y, line_dash="dash", line_color="gray",
                  annotation_text=f"中位数 {median_y:.1f}", annotation_position="top right")
    
    # 6. 加象限标注(可选,通过判断四象限分布情况自动决定是否加)
    # 右上角: 高X高Y(优质区) / 左下角: 低X低Y(待改善区)
    quadrant_counts = {
        "右上(高价高评)": len(df[(df[x_col] > median_x) & (df[y_col] > median_y)]),
        "右下(高价低评)": len(df[(df[x_col] > median_x) & (df[y_col] < median_y)]),
        "左上(低价高评)": len(df[(df[x_col] < median_x) & (df[y_col] > median_y)]),
        "左下(低价低评)": len(df[(df[x_col] < median_x) & (df[y_col] < median_y)])
    }
    
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        plot_bgcolor="white"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    st.info(f"💡 {insight}")
    
    # 展示象限分布统计
    with st.expander("查看象限分布"):
        for quadrant, count in quadrant_counts.items():
            pct = count / len(df) * 100
            st.write(f"**{quadrant}**: {count} 个品类({pct:.1f}%)")
    
    with st.expander("查看原始数据"):
        st.dataframe(df)

【任务二:在 validators.py 中加入气泡图校验】

在 validate_chart_type 中加入:
- x_col 不是数值: 降级为 bar + 警告"气泡图 X 轴必须是数值字段"
- y_col 不是数值: 降级为 bar + 警告"气泡图 Y 轴必须是数值字段"
- 数据量 < 3: 降级为 table + 警告"气泡图数据量过少(< 3条),使用表格展示"
- 数据量 > 200: 不降级,显示提示"数据量较大,气泡可能重叠,建议增加过滤条件"

【在 AGENT_SYSTEM_PROMPT 中加入气泡图选择指引】

```
气泡图(bubble)选择条件(同时满足才用):
1. 用户问题涉及"三个数值维度"的关系分析
2. 有合适的"大小"语义字段(如销量、金额、用户数)
3. 数据点数量在 5-100 之间(太少没意义,太多重叠)

调用气泡图时必须填写 bubble_options.size_col,
这是区别于普通散点图的关键参数。

典型触发词: "三维分析""大小表示""气泡""...和...和...的关系"
```

【约束】
- 中位数参考线必须显示(这是气泡图的标准配置,帮助用户定位象限)
- 象限统计 expander 是可选展示,不影响主图
- size_col 包含负数/零时不报错,自动偏移处理
- 不要在 figure 里直接写文字标注每个气泡(数据点多时会很乱,用 hover 代替)

【测试用例】
基于 Olist 数据测试:
"用气泡图分析各品类的平均价格、平均评分和订单量的关系"

→ 预期:
  X 轴: avg_price(平均价格)
  Y 轴: avg_score(平均评分)
  气泡大小: order_count(订单量)
  气泡标签: category(品类名,悬停显示)
  有中位数参考线划分四个象限

【交付方式】
1. 先写气泡图分支的完整代码(含中位数线和象限 expander)
2. 然后更新 validators.py
3. 更新 AGENT_SYSTEM_PROMPT 中的气泡图选择规则
4. 告诉我:如果 x_col 和 size_col 是同一个字段,代码会怎么处理?
```

**✅ 气泡图完成标志:**
- 气泡大小由 `size_col` 控制,不是固定大小
- 有中位数参考线(X 和 Y 方向各一条)
- 悬停显示完整字段信息
- 有象限分布统计 expander
- 负值自动偏移,不报错

**基于 Olist 的测试场景:**

```
用户: "各品类平均价格、平均评分、订单量三者的关系如何?用气泡图展示"

Agent 执行:
Step 1: query_database
  SQL: SELECT product_category_name AS category,
              AVG(price) AS avg_price,
              AVG(review_score) AS avg_score,
              COUNT(DISTINCT order_id) AS order_count
       FROM ...(多表 JOIN)
       GROUP BY category HAVING COUNT(*) > 50
       ORDER BY order_count DESC LIMIT 30
  intent: "品类三维对比数据"

Step 2: make_chart
  chart_type: "bubble"
  x_col: "avg_price"
  y_col: "avg_score"
  x_axis_label: "平均价格(BRL)"
  y_axis_label: "平均评分(1-5分)"
  result_key: "品类三维对比数据"
  title: "各品类价格-评分-销量气泡图(2017-2018)"
  bubble_options: {
    "size_col": "order_count",
    "label_col": "category",
    "size_max": 60
  }
  insight: "高价品类评分不一定高;订单量最大的品类集中在中低价格段;右上象限(高价高评)的品类值得重点关注"
```

---

### 4.1.4 [v3 新增] 三种图表的 System Prompt 更新

在 `附录 A · Agent System Prompt 最终版` 的"图表选择"规则中,将原有内容替换为完整版:

```python
# 在 AGENT_SYSTEM_PROMPT 的图表选择规则区域替换为:

图表选择规则(代码层会自动校验,但请尽量选对):

# 原有 10 种图表规则(保持不变):
- 不要用 3D 饼图(视觉失真)
- 类别 > 5 个不要用 pie/donut,改用 barh
- 时间序列优先 line,X 轴必须是时间字段
- 不同量级双指标(如订单量+转化率)用 combo 双轴图
- 不确定时优先 bar 或 table(最不容易出错)

# [v3 新增] 三种新图表的选择规则:
词云图(wordcloud):
- 用户问题包含"词云""高频词""关键词可视化""文字图"时使用
- 数据中有文本字段(如评论、描述)或已统计的词频字段
- wordcloud_options 必须填 text_col 或 (word_col + freq_col) 之一
- 语言选择: 中文数据填 'zh',葡萄牙语填 'pt',不确定填 'auto'

漏斗图(funnel):
- 用户问题包含"漏斗""转化""流失""各阶段""流程"时使用
- 数据必须有明确的阶段顺序字段和对应数量字段
- funnel_options 必须填 stage_col 和 value_col
- 阶段数控制在 2-10 之间(超过自动降级)

气泡图(bubble):
- 用户问题同时涉及"三个数值维度"且其中一个有"大小/规模"语义时使用
- 典型模式: "A 和 B 的关系,用 C 表示规模"
- bubble_options 必须填 size_col
- 建议同时填 label_col,让用户悬停时能看到数据点的名称
- 数据点在 5-100 条之间效果最好

调用任何图表时都必须填 result_key,明确指定数据来源。
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

### 4.3 Day 22:主动洞察 + 报告生成(Word + PDF 导出) [v2 修订 + v3 新增]

> ⚠️ **v2 修订说明(对应问题 5)**
>
> v1 的报告只能生成 Markdown,在 Streamlit 里看很好,
> 但发给领导/同事时没人用 `.md` 文件。v2 加入了 Word 导出。

> 🟢 **v3 新增说明**
>
> v2 的 Word 报告解决了"发给同事"的问题,但还有两个场景没覆盖:
> 1. **发给外部**:PDF 是跨平台标准格式,格式不会在对方电脑上错乱
> 2. **内容完整性**:Word 报告只有文字和表格,**图表无法自动嵌入**;
>    PDF 报告可以把本轮所有 Plotly 图表截图后嵌入文档,做到"所见即所得"
>
> **v3 修复方案:**
> - 新增 `src/report_builder.py` 模块,统一管理 Word 和 PDF 的构建逻辑
> - PDF 生成管线:`Markdown → HTML → (图表 PNG 嵌入) → PDF`
> - 图表导出:`kaleido` 把 Plotly 图表渲染为 PNG bytes,Base64 编码后嵌入 HTML
> - `output_format` 新增 `"pdf"` 和 `"all"` 选项

**📋 Prompt 模板(完整版,发给 Claude Code):**

```
我已完成 Week3 前面所有任务。现在做 Day 22 的最后三个功能:
主动洞察 + Word 报告 + PDF 报告(v3 新增)。

【技术栈】
- Word 导出: python-docx
- PDF 导出: weasyprint + markdown + kaleido
- 统一封装在: src/report_builder.py

---

【任务 1: 主动洞察(修改 prompts.py)】

在 AGENT_SYSTEM_PROMPT 中加入以下规则(插入到"主动洞察"区域):

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
- 不超过 3 个建议,用数字编号
- 不要重复推荐上一轮已分析过的方向
```

---

【任务 2: 新建 src/report_builder.py】

这个模块统一管理 Word 和 PDF 两种报告格式的构建逻辑。
把原本打算写在 tools.py 里的 markdown_to_word 和新增的 PDF 逻辑
都移到这里,tools.py 只调用 report_builder 的函数。

请实现以下函数:

# ─── 函数 1: markdown_to_word ───────────────────────────────────────

def markdown_to_word(markdown_content: str, title: str) -> bytes:
    """
    把 Markdown 字符串转成格式化的 Word 文档,返回 bytes。
    
    格式规范:
    - 文档标题:  24pt 加粗居中,段前间距 18pt
    - 一级标题(# ):  18pt 加粗,段前 12pt,段后 6pt
    - 二级标题(## ): 14pt 加粗,段前 8pt,段后 4pt
    - 三级标题(###): 12pt 加粗,段前 6pt
    - 正文:      11pt,行间距 1.3 倍,首行不缩进
    - 加粗(**text**): 对应 Word Run 加粗
    - 项目符号(-):  转为 Word 项目符号段落,缩进 0.5cm
    - Markdown 表格(|---|): 转为 Word 表格,表头行加灰色底色(#D9D9D9)
    - 水平线(---): 转为段落边框线
    - 页眉: 报告标题(右对齐)
    - 页脚: 生成日期(左) + 页码(右)
    
    实现思路:
    1. 按行解析 Markdown(正则匹配各元素类型)
    2. 依次调用 python-docx API 写入对应格式
    3. 图表在 Word 中暂时不嵌入(Word 格式不支持交互式图表,
       只在报告末尾加注: "本报告图表请在 AI Agent 界面查看")
    
    返回: bytes(BytesIO.getvalue())
    """
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    import re
    from io import BytesIO
    from datetime import datetime
    pass

# ─── 函数 2: export_chart_as_png ────────────────────────────────────

def export_chart_as_png(fig, width: int = 900, height: int = 450) -> bytes | None:
    """
    把 Plotly Figure 导出为 PNG bytes。
    依赖 kaleido 引擎,找不到时返回 None(不报错,报告继续生成)。
    
    参数:
    - fig: plotly.graph_objects.Figure 对象
    - width/height: 导出分辨率(像素)
    
    返回: PNG bytes 或 None
    
    实现:
    try:
        return fig.to_image(format="png", width=width, height=height, scale=2)
    except Exception as e:
        print(f"⚠️ 图表导出失败(可能未安装 kaleido): {e}")
        return None
    """
    pass

# ─── 函数 3: build_html_report ──────────────────────────────────────

def build_html_report(
    markdown_content: str,
    title: str,
    chart_figures: list,      # list of plotly Figure 对象
    chart_captions: list      # list of str,每张图的标题
) -> str:
    """
    把 Markdown 内容 + Plotly 图表 合并成一个完整的 HTML 字符串。
    这是 PDF 生成的中间产物。
    
    实现步骤:
    
    Step 1: 用 markdown 库把 Markdown 转成 HTML 片段
        import markdown
        body_html = markdown.markdown(
            markdown_content,
            extensions=['tables', 'fenced_code']  # 支持表格和代码块
        )
    
    Step 2: 把每张 Plotly 图表导出为 PNG,Base64 编码后嵌入 <img> 标签
        for fig, caption in zip(chart_figures, chart_captions):
            png_bytes = export_chart_as_png(fig)
            if png_bytes:
                b64 = base64.b64encode(png_bytes).decode()
                img_tag = f'<figure><img src="data:image/png;base64,{b64}" '
                          f'style="width:100%;max-width:800px;"/>'
                          f'<figcaption>{caption}</figcaption></figure>'
                body_html += img_tag
            else:
                body_html += f'<p><em>[图表"{caption}"无法嵌入,请在 Agent 界面查看]</em></p>'
    
    Step 3: 包裹完整 HTML + CSS 样式
    
    CSS 样式规范:
    - 字体: 优先使用系统中文字体('Microsoft YaHei', 'SimHei', 'STHeiti', sans-serif)
    - 页面: A4 纸宽度(210mm),左右边距 20mm,上下边距 15mm
    - 正文字号: 11pt,行高 1.6
    - 一级标题: 18pt 加粗,上边距 20pt,下边距 8pt
    - 二级标题: 14pt 加粗,上边距 14pt,下边距 6pt
    - 表格: 宽度 100%,有边框,表头行加灰色底色(#F2F2F2)
    - 图片: 最大宽度 100%,居中显示
    - 代码块: 灰色背景,等宽字体
    - 页眉: 报告标题(通过 @page CSS 设置,weasyprint 支持)
    - 页脚: 生成日期 + 页码
    
    HTML 模板结构:
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>
            @page {{
                size: A4;
                margin: 15mm 20mm;
                @top-right {{ content: "{title}"; font-size: 9pt; color: #888; }}
                @bottom-right {{ content: "第 " counter(page) " 页"; font-size: 9pt; }}
                @bottom-left {{ content: "{generated_date}"; font-size: 9pt; color: #888; }}
            }}
            body {{ font-family: 'Microsoft YaHei', 'SimHei', 'STHeiti', sans-serif;
                    font-size: 11pt; line-height: 1.6; color: #333; }}
            h1 {{ font-size: 18pt; font-weight: bold; ... }}
            h2 {{ font-size: 14pt; ... }}
            table {{ width: 100%; border-collapse: collapse; ... }}
            th {{ background-color: #F2F2F2; ... }}
            td, th {{ border: 1px solid #DDD; padding: 6px 10px; }}
            img {{ max-width: 100%; display: block; margin: 10px auto; }}
            figure {{ text-align: center; margin: 16px 0; }}
            figcaption {{ font-size: 9pt; color: #666; margin-top: 4px; }}
            code {{ background: #F5F5F5; padding: 2px 6px; border-radius: 3px; }}
            pre {{ background: #F5F5F5; padding: 12px; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <h1 style="text-align:center">{title}</h1>
        <p style="text-align:center;color:#888;font-size:9pt">
            生成时间: {generated_date}
        </p>
        <hr/>
        {body_html}
    </body>
    </html>
    
    返回: 完整 HTML 字符串
    """
    pass

# ─── 函数 4: html_to_pdf ────────────────────────────────────────────

def html_to_pdf(html_content: str) -> bytes:
    """
    用 weasyprint 把 HTML 字符串渲染成 PDF bytes。
    
    实现:
    from weasyprint import HTML, CSS
    from io import BytesIO
    
    buf = BytesIO()
    HTML(string=html_content).write_pdf(buf)
    return buf.getvalue()
    
    注意:
    - weasyprint 在 Windows 上需要 GTK 运行时,见环境准备说明
    - 找不到 weasyprint 时抛出 ImportError,由调用方处理并显示友好提示
    
    返回: PDF bytes
    """
    pass

# ─── 函数 5: markdown_to_pdf (对外入口函数) ─────────────────────────

def markdown_to_pdf(
    markdown_content: str,
    title: str,
    chart_figures: list = None,
    chart_captions: list = None
) -> bytes:
    """
    完整的 Markdown → PDF 管线,对外暴露的唯一入口。
    
    内部调用:
    1. build_html_report(markdown_content, title, chart_figures, chart_captions)
    2. html_to_pdf(html_str)
    3. 返回 PDF bytes
    
    chart_figures 和 chart_captions 为可选参数:
    - 不传时:生成纯文字+表格的 PDF(无图表截图)
    - 传入时:把 Plotly 图表截图嵌入 PDF 对应位置
    
    返回: PDF bytes
    """
    chart_figures = chart_figures or []
    chart_captions = chart_captions or []
    html_str = build_html_report(markdown_content, title, chart_figures, chart_captions)
    return html_to_pdf(html_str)

【任务 3: 更新 tools.py 中的 generate_report 工具】

更新 Function Calling Schema:

{
    "type": "function",
    "function": {
        "name": "generate_report",
        "description": "把当前会话的所有分析整合成完整报告。\n支持三种格式:\n- markdown: 在页面内展示\n- word: 下载 .docx(含格式,适合编辑)\n- pdf: 下载 .pdf(含图表截图,适合发送/存档)\n- all: 同时提供 Word 和 PDF 两个下载按钮\n建议默认用 all,让用户自行选择。",
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
                    },
                    "description": "要包含的章节列表"
                },
                "audience": {
                    "type": "string",
                    "enum": ["management","operation","technical"],
                    "description": "management: 管理层,结论优先,无技术细节 / operation: 运营,可执行建议优先 / technical: 技术,完整方法论"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown","word","pdf","all"],
                    "description": "输出格式:\n- markdown: 只在页面展示,不下载\n- word: 只下载 .docx\n- pdf: 只下载 .pdf(含图表截图)\n- all: 页面展示 + Word 下载 + PDF 下载(默认推荐)",
                    "default": "all"
                },
                "embed_charts": {
                    "type": "boolean",
                    "description": "PDF 中是否嵌入图表截图。true=嵌入(文件较大,内容完整); false=只有文字和表格(文件小)。默认 true。",
                    "default": true
                }
            },
            "required": ["report_title", "include_sections"]
        }
    }
}

更新 generate_report 函数实现:

def generate_report(report_title, include_sections,
                    audience="operation", output_format="all",
                    embed_charts=True):
    """
    完整实现:
    
    Step 1: 从 session_state 收集本轮所有分析内容
        - messages: 对话历史(用来让 LLM 整合)
        - query_results: 所有查询结果的 DataFrame 摘要
        - chart_registry: 本轮所有已显示的 Plotly Figure 对象
          (需要在 make_chart 里把 fig 存入 session_state['chart_registry'])
    
    Step 2: 调用 LLM 生成 Markdown 格式的报告内容
        - 根据 audience 调整风格(管理层简洁/运营可执行/技术详细)
        - 根据 include_sections 决定包含哪些章节
        - LLM 不需要重新分析数据,只是把已有结论整合成报告格式
    
    Step 3: 根据 output_format 生成对应输出
        
        if output_format in ("markdown", "all"):
            st.markdown(content)
        
        if output_format in ("word", "all"):
            docx_bytes = report_builder.markdown_to_word(content, report_title)
            st.download_button(
                label="📄 下载 Word 报告",
                data=docx_bytes,
                file_name=f"{report_title}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="download_word"
            )
        
        if output_format in ("pdf", "all"):
            # 获取本轮图表
            figures = []
            captions = []
            if embed_charts:
                chart_reg = st.session_state.get('chart_registry', [])
                figures  = [item['fig']     for item in chart_reg]
                captions = [item['caption'] for item in chart_reg]
            
            try:
                pdf_bytes = report_builder.markdown_to_pdf(
                    content, report_title, figures, captions
                )
                st.download_button(
                    label="📑 下载 PDF 报告(含图表)",
                    data=pdf_bytes,
                    file_name=f"{report_title}.pdf",
                    mime="application/pdf",
                    key="download_pdf"
                )
            except ImportError:
                st.warning("⚠️ PDF 生成需要安装 weasyprint。"
                           "Windows 用户请参考 README 的安装说明,或使用 Word 格式。")
    """
    pass

【任务 4: 在 make_chart 里注册图表到 chart_registry】

make_chart 每次成功渲染图表后,把 fig 存入 session_state:

# 在 st.plotly_chart(fig, ...) 之后加入:
if 'chart_registry' not in st.session_state:
    st.session_state['chart_registry'] = []
st.session_state['chart_registry'].append({
    'fig': fig,
    'caption': title,
    'timestamp': datetime.now().isoformat()
})

同时在 sidebar 的"清空对话"按钮逻辑里加上:
st.session_state.pop('chart_registry', None)

【约束】

- report_builder.py 中所有函数都不能依赖 Streamlit
  (纯 Python,方便单元测试和复用)
- html_to_pdf 必须用 try-except 包裹 import weasyprint,
  ImportError 时抛出清晰的错误信息给调用方处理
- export_chart_as_png 找不到 kaleido 时返回 None,不抛异常
- PDF 中文字体优先用系统字体,找不到时 weasyprint 会自动降级,
  不需要手动指定字体文件路径(与词云不同)
- Word 报告不嵌入图表(python-docx 嵌入 Plotly 图需要额外的截图步骤,
  复杂度高,在 Word 末尾加一行注释即可)
- chart_registry 按时间顺序存储,PDF 中图表在报告正文之后按顺序附上
- embed_charts=False 时跳过 kaleido 导出,PDF 只有文字和表格,生成更快

【交付方式】

请严格按以下顺序,每完成一步停下来等我确认:

Step 1: 实现 report_builder.py 中的 markdown_to_word
        用一段含有一级标题、二级标题、表格、加粗、列表的 Markdown 测试,
        确认 Word 格式正确后再继续

Step 2: 实现 export_chart_as_png
        用一个简单的 px.bar 测试,确认返回非空 bytes

Step 3: 实现 build_html_report
        先不嵌图表,只测试纯文字+表格的 HTML 输出是否正确

Step 4: 实现 html_to_pdf
        基于 Step 3 的 HTML,生成 PDF 检查排版

Step 5: 测试图表嵌入:传入 1 张 Plotly 图表,确认 PNG 嵌入 PDF 后显示正常

Step 6: 更新 tools.py 中的 generate_report(Schema + 实现)
        同时更新 make_chart 加入 chart_registry 注册逻辑

Step 7: 端到端测试:
        用户说"生成本次分析的完整报告,格式选 all"
        → 页面显示 Markdown 内容
        → 出现"下载 Word"和"下载 PDF"两个按钮
        → Word 文件格式正确
        → PDF 文件包含图表截图

Step 8: 告诉我:如果用户在 Windows 上没有安装 weasyprint,
        UI 上会出现什么提示?用户应该怎么操作?
```

**✅ Week 3 Day 22 完成标志:**
- 主动洞察在每轮分析后推荐具体的下一步(带数字引用)
- `generate_report` 支持 `markdown / word / pdf / all` 四种格式
- Word 报告:含标题层级、加粗、表格、页眉页脚格式
- PDF 报告:含文字、表格、Plotly 图表截图,A4 纸排版
- 图表自动注册到 `chart_registry`,生成报告时统一嵌入 PDF
- Windows 下 weasyprint 缺失时有友好提示,不报红色错误
- "清空对话"同时清空 `chart_registry`

**完整生成报告的 Agent 执行流程(End-to-End):**

```
用户: "把本次分析生成完整报告,格式要 all"
        ↓
Agent 调用 generate_report:
  report_title: "Olist 2017年Q4销售分析报告"
  include_sections: ["背景","核心发现","详细分析","归因结论","建议"]
  audience: "management"
  output_format: "all"
  embed_charts: true
        ↓
Step 1: 从 session_state 读取
  - 对话历史(messages)
  - 查询结果摘要(query_results)
  - 本轮图表(chart_registry,含 3 张 Plotly 图)
        ↓
Step 2: LLM 整合成 Markdown 报告内容
        ↓
Step 3a: st.markdown() → 页面展示
Step 3b: markdown_to_word() → 📄 下载 Word 按钮
Step 3c: markdown_to_pdf()
         ├── build_html_report() 把 3 张图表导出 PNG 嵌入 HTML
         └── html_to_pdf() 用 weasyprint 渲染
         → 📑 下载 PDF 按钮(含图表截图)
```

**PDF 报告内容示例(结构):**

```
────────────────────────────────────
  Olist 2017年Q4销售分析报告
  生成时间: 2026-05-03 14:30
────────────────────────────────────

## 一、背景

本报告基于 Olist 电商平台 2017 年 Q4 数据分析...

## 二、核心发现

| 指标       | 数值      | 环比变化 |
|-----------|----------|---------|
| 总销售额   | R$1,234万 | +12.3%  |
| 订单数     | 28,432   | +8.7%   |
| 客单价     | R$433    | +3.3%   |

## 三、详细分析

...

[图1: 2017年Q4各州订单量对比]
[此处嵌入柱状图截图]

[图2: Top10品类销售额排名]
[此处嵌入横向条形图截图]

## 四、归因结论

...

## 五、建议

...
────────────────────────────────────
                          第 1 页 / 共 3 页
```

**✅ Week 3 完成标志:**
- 图表有自动校验,LLM 选错类型会自动降级并显示提示
- make_chart 用 result_key 精确指定数据,不会画错历史数据
- 归因诊断工具能正确计算贡献度,置信度由代码评估而非 LLM 自评
- 主动洞察在每轮分析后推荐具体的下一步(带数字引用)
- 能生成 Word 格式的分析报告并下载(含格式化标题/表格/页眉页脚)
- **[v3]** 能生成 PDF 格式的分析报告并下载(含 Plotly 图表截图嵌入)
- **[v3]** `generate_report` 支持 `markdown / word / pdf / all` 四种格式
- **[v3]** weasyprint 未安装时有友好降级提示,不显示红色报错
- **[v3]** 图表自动注册到 `chart_registry`,生成报告时统一提取嵌入 PDF

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

技术栈: Python | Streamlit | DeepSeek API | DuckDB | Plotly | wordcloud | python-docx | weasyprint
GitHub: github.com/xxx | Demo: xxx.streamlit.app

核心亮点:
• 设计 Agent 架构,通过 Function Calling 实现工具调用 + 多步规划 + 多轮记忆
• 用带意图标签的查询缓存机制解决跨轮数据污染问题,确保图表数据准确
• 用 DuckDB 作为统一查询层,支持 Excel / CSV / 数据库的统一 SQL 访问
• 实现归因诊断工具,自动完成指标拆解 + 维度下钻 + 贡献度量化(置信度由代码评估)
• 支持 13 种图表类型(含词云图/漏斗图/气泡图),带自动类型校验与降级机制
• 支持一键生成 Word 和 PDF 双格式分析报告,PDF 自动嵌入本轮所有图表截图
```

**面试话术准备 9 个问题:**

1. 这个项目的设计思路是什么?
2. 为什么选 DeepSeek?为什么不用 LangChain?
3. 如何让 Agent 能处理复杂多步问题?
4. 归因诊断工具内部是怎么工作的?
5. 这个 Agent 的局限性是什么?如果在公司落地怎么改进?
6. **你在做这个项目过程中发现了哪些设计问题,怎么修复的?**
7. **为什么不直接把数据传给 Claude/Gemini 来分析?**
8. **词云图、漏斗图、气泡图分别适合什么场景?你是怎么设计它们的参数 Schema 的?**
9. **[v3 新增]** 你的报告支持 Word 和 PDF 两种格式,两者有什么区别?PDF 里的图表是怎么嵌入的?

**问题 9 参考回答:**

> "Word 适合需要继续编辑的场景,用 python-docx 生成,格式上能保留标题层级和表格。
> PDF 适合直接发送存档的场景,格式固定不会错乱。
>
> PDF 里图表嵌入的技术路径是:每次 make_chart 渲染图表时,
> 把 Plotly Figure 对象注册到 chart_registry。生成报告时,
> 用 kaleido 把每个 Figure 渲染成 PNG bytes,Base64 编码后嵌入 HTML 的 img 标签。
> 最后 weasyprint 把完整 HTML 渲染成 PDF。
>
> 这条管线的设计考虑了降级处理:kaleido 找不到时图表跳过但报告继续生成;
> weasyprint 在 Windows 上安装复杂,代码里有 ImportError 捕获和友好提示,
> 不会让用户看到红色报错。"

> 问题 6 和 7 来自 v2。问题 8、9 是 v3 新增,展示图表设计和报告工程的深度。

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
5. generate_report: 生成分析报告(支持 Markdown 展示 / Word 下载 / PDF 下载含图表截图)

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
- [v3] 文本词频可视化用 wordcloud,wordcloud_options 必须填 text_col 或 word_col+freq_col
- [v3] 流程转化分析用 funnel,funnel_options 必须填 stage_col 和 value_col
- [v3] 三维数值关系分析用 bubble,bubble_options 必须填 size_col

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
- [ ] 至少 13 种图表类型可用(含 v3 新增的词云/漏斗/气泡)
- [ ] 图表类型校验层生效(饼图 >5 类自动降级)
- [ ] make_chart 用 result_key 指定数据源
- [ ] 能处理多步分析问题
- [ ] 归因诊断工具能跑通(含贡献度计算)
- [ ] 置信度由代码规则评估,不是 LLM 自评
- [ ] 能生成 Word 报告并下载(含格式化标题/表格/页眉页脚)
- [ ] **[v3]** 能生成 PDF 报告并下载(含 Plotly 图表截图嵌入)
- [ ] **[v3]** `generate_report` 的 `output_format` 支持四种值:markdown/word/pdf/all
- [ ] **[v3]** `chart_registry` 在每次 make_chart 时自动注册图表
- [ ] **[v3]** weasyprint 未安装时显示友好提示而非红色报错
- [ ] 多轮对话上下文连贯
- [ ] 只有大查询(>10万行)才弹确认框
- [ ] 错误能友好提示
- [ ] **[v3]** 词云图能正确渲染并提供 PNG 下载
- [ ] **[v3]** 中文词云在 Windows/Mac/Linux 三平台字体正确
- [ ] **[v3]** 漏斗图自动排序 + 转化率标注 + 层间流失显示
- [ ] **[v3]** 气泡图有中位数参考线 + 象限统计 + 悬停标签
- [ ] **[v3]** 三种新图表的 validators 校验规则全部生效

### 工程质量
- [ ] 代码有详细注释
- [ ] 关键函数有 docstring
- [ ] requirements.txt 包含 python-docx、wordcloud、matplotlib、weasyprint、markdown、kaleido
- [ ] validators.py 有单元测试(含三种新图表的校验测试)
- [ ] chart_utils.py 有单元测试(独立于 Streamlit 可运行)
- [ ] report_builder.py 有单元测试(markdown_to_word / build_html_report 各一个)
- [ ] assets/fonts/ 目录存在(README 中有字体配置说明)
- [ ] .env.example 存在
- [ ] .gitignore 排除敏感文件
- [ ] README 包含 weasyprint Windows 安装说明

### 求职准备
- [ ] 项目部署上线,有公开 URL
- [ ] GitHub README 包含"为什么不直接用 Claude/Gemini"一节
- [ ] 至少 1 篇技术复盘文章发布
- [ ] 3-5 分钟 demo 视频录制完成(包含 PDF 报告下载演示片段)
- [ ] 简历项目描述写好(含 v3 PDF 报告能力)
- [ ] 8 个面试问题准备好(含问题 6、7、8)

---

完成所有这些,你就有了一个完整的、能讲能演示的 AI 数据分析 Agent 求职作品。

祝你拿到心仪的 offer 🎯

---

## 附录 C · [v3 新增] 三种新图表的常见问题排查

### 词云图

**Q: 词云显示方块(□□□)怎么办?**

A: 中文字体缺失,按顺序排查:
1. 确认 `assets/fonts/SimHei.ttf` 存在(这是最可靠的方式)
2. `get_font_path()` 加 `print` 输出,确认返回的路径真实存在
3. Streamlit Cloud 部署时在项目根目录加 `packages.txt`,内容:
   ```
   fonts-wqy-zenhei
   ```
4. 葡萄牙语数据不需要中文字体,只有输出的关键词是中文时才需要

**Q: 词云生成很慢怎么办?**

A: `wordcloud` 库本身的布局算法比较耗时,可以:
1. 降低 `max_words`(80 比 200 快很多)
2. 降低 `width × height`(900×450 比 1800×900 快 4 倍)
3. 预先统计词频再传入(格式二),跳过分词步骤
4. 把词云生成放在 `st.spinner` 里,提示用户稍等

**Q: 词云出现大量无意义词(的/了/是...)怎么办?**

A: 停用词问题:
1. 中文: jieba 有内置停用词,另外在 `WordCloud` 里加 `stopwords` 参数
2. 葡萄牙语: 手动维护一个停用词列表(de/da/do/em/que/para...)
3. 通用处理: 过滤长度 ≤ 1 的词、纯数字词

---

### 漏斗图

**Q: 漏斗各层不是从大到小排列怎么办?**

A: 代码里的 `sort_values(ascending=False)` 会自动排序,但要确认:
1. `value_col` 是数值类型,不是字符串
2. 如果用户的"漏斗"阶段有业务顺序(如 created → approved → shipped),
   需要先给阶段加数字前缀再排序:
   ```sql
   CASE order_status
       WHEN 'created'   THEN '1.已创建'
       WHEN 'approved'  THEN '2.已批准'
       ...
   END AS stage
   ```

**Q: 漏斗图层间转化率标注位置错乱怎么办?**

A: `go.Figure annotation` 的坐标系问题:
- `x=0.5` 是 paper 坐标(相对整个图表宽度),不是数据坐标
- `y=i - 0.5` 是近似位置,实际位置取决于漏斗层的高度
- 如果标注重叠,调整 `y` 的计算公式或改用 `textinfo` 把信息嵌在漏斗层内

---

### 气泡图

**Q: 气泡都挤在一起看不清怎么办?**

A: 几种处理方式:
1. 减小 `size_max`(从 60 降到 30)
2. 对 `size_col` 做对数变换: `df['size_log'] = np.log1p(df[size_col])`
3. 过滤异常大的数据点(头部效应导致其他点都很小)
4. 减少数据点数量(SQL 里加 `LIMIT` 或提高 `HAVING COUNT > N` 的阈值)

**Q: 气泡图 X/Y 轴有极端值影响整体分布怎么办?**

A: 在 `fig.update_layout` 里手动设置轴范围:
```python
fig.update_xaxes(range=[df[x_col].quantile(0.05), df[x_col].quantile(0.95)])
fig.update_yaxes(range=[df[y_col].quantile(0.05), df[y_col].quantile(0.95)])
```
同时显示提示:"已排除 5% 极端值以提高图表可读性"

**Q: 中位数参考线和数据点标签重叠怎么办?**

A: 气泡图不建议直接标注每个气泡的名称(数据点多时会很乱),正确做法:
- 气泡名称通过 `hover_name` 悬停显示
- 如果确实需要标注,只标注最大/最小的几个气泡:
  ```python
  top3 = df.nlargest(3, size_col)
  for _, row in top3.iterrows():
      fig.add_annotation(x=row[x_col], y=row[y_col], text=row[label_col], ...)
  ```

---

## 附录 D · [v3 新增] PDF 报告常见问题排查

### 安装问题

**Q: Windows 上安装 weasyprint 报错怎么办?**

A: weasyprint 依赖 GTK 运行时,Windows 原生安装较复杂。按优先级选择:

方案 1(推荐):用 **WSL2** 开发
```bash
# 在 WSL2 Ubuntu 环境里安装
sudo apt-get install python3-weasyprint
pip install weasyprint
```

方案 2:按官方文档安装 GTK
- 访问 https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows
- 下载 GTK 运行时安装包(约 150MB)
- 安装后重启,再 `pip install weasyprint`

方案 3:用 **fpdf2** 替代(纯 Python,无外部依赖)
```bash
pip install fpdf2
```
fpdf2 不能直接渲染 HTML,需要手动逐段写入 PDF。
格式比 weasyprint 简单,但不需要 GTK,所有平台开箱即用。
fpdf2 版本的 `markdown_to_pdf` 实现思路:
```python
from fpdf import FPDF
import re

def markdown_to_pdf_fpdf(markdown_content: str, title: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 添加中文字体(需要 TTF 文件)
    pdf.add_font('SimHei', '', 'assets/fonts/SimHei.ttf', uni=True)
    
    for line in markdown_content.split('\n'):
        if line.startswith('# '):
            pdf.set_font('SimHei', size=18)
            pdf.cell(0, 12, line[2:], ln=True)
        elif line.startswith('## '):
            pdf.set_font('SimHei', size=14)
            pdf.cell(0, 10, line[3:], ln=True)
        elif line.strip():
            pdf.set_font('SimHei', size=11)
            pdf.multi_cell(0, 7, line)
    
    return pdf.output(dest='S').encode('latin-1')
```
注意:fpdf2 嵌入图表需要先把 PNG bytes 写入临时文件再引用,
比 weasyprint 的 Base64 方式稍麻烦。

**Q: pip install kaleido 之后图表还是导出失败?**

A: kaleido 依赖 Chromium 内核,常见问题:
1. `pip install kaleido` 之后需要**重启 Python 进程**
2. 检查版本:kaleido 0.2.x 和 1.x 的 API 有差异
   - Plotly 5.x 推荐用 kaleido 0.2.1: `pip install kaleido==0.2.1`
3. Linux 服务器上可能缺少 chromium 依赖:
   ```bash
   sudo apt-get install -y chromium-browser
   ```
4. Streamlit Cloud 部署时需在 `packages.txt` 加:
   ```
   chromium-driver
   ```

---

### 生成质量问题

**Q: PDF 中中文显示为方块怎么办?**

A: weasyprint 中文字体问题与词云不同,处理方式也不同:

1. **CSS 字体声明法(推荐)**:在 `build_html_report` 的 CSS 里声明字体栈:
   ```css
   body { font-family: 'Microsoft YaHei', 'SimHei', 'STHeiti',
                        'WenQuanYi Zen Hei', sans-serif; }
   ```
   weasyprint 会按顺序找系统字体,找到一个能显示中文的就用

2. **嵌入字体文件法**:在 CSS 里用 `@font-face` 嵌入 TTF 文件:
   ```css
   @font-face {
       font-family: 'CustomFont';
       src: url('assets/fonts/SimHei.ttf');
   }
   body { font-family: 'CustomFont', sans-serif; }
   ```

3. **Streamlit Cloud 部署时**:在 `packages.txt` 加:
   ```
   fonts-wqy-zenhei
   fonts-noto-cjk
   ```

**Q: PDF 里的图表截图模糊怎么办?**

A: 调高 kaleido 的导出分辨率:
```python
# 在 export_chart_as_png 里调整参数
fig.to_image(format="png", width=1200, height=600, scale=3)
# scale=3 相当于 3 倍分辨率,适合 A4 打印
# 但文件会变大,建议 scale=2 作为平衡点
```

**Q: PDF 页面排版乱(图表溢出边界/表格断行)怎么办?**

A: 调整 CSS 中的页面设置:
```css
@page {
    size: A4;
    margin: 20mm 25mm;   /* 上下/左右边距,太小容易溢出 */
}
img {
    max-width: 100%;      /* 图片不超过页宽 */
    page-break-inside: avoid;  /* 图片不在页面中间断开 */
}
table {
    page-break-inside: avoid;  /* 小表格不断页 */
}
h2 {
    page-break-before: auto;   /* 二级标题前不强制换页 */
}
```

**Q: PDF 文件太大怎么办?**

A: 几种减小体积的方式:
1. 降低图表导出分辨率:`scale=1` 替代 `scale=2`
2. 减小图表尺寸:`width=800, height=400` 替代 `width=1200, height=600`
3. 对于图表数量多的报告,`embed_charts=False` 生成无图版 PDF
4. 图表超过 5 张时,只嵌入用户标记为"重要"的图表
   (可以在 make_chart 里加一个 `is_key_chart: bool` 参数控制)

---

### 部署问题

**Q: Streamlit Cloud 上 PDF 生成失败怎么办?**

A: Streamlit Cloud 是 Linux 环境,检查:

1. `requirements.txt` 包含 `weasyprint` 和 `kaleido`
2. `packages.txt`(系统包)包含:
   ```
   libpango-1.0-0
   libpangocairo-1.0-0
   libgdk-pixbuf2.0-0
   libffi-dev
   shared-mime-info
   fonts-wqy-zenhei
   chromium-driver
   ```
3. 如果上述系统包安装后还失败,改用 fpdf2 方案(见上方 Windows 部分)

**Q: 本地能生成 PDF,部署到 Streamlit Cloud 后不行?**

A: 原因通常是 Streamlit Cloud 的 Linux 容器缺少系统依赖。
最可靠的诊断方式是在 `html_to_pdf` 里加日志:
```python
def html_to_pdf(html_content: str) -> bytes:
    try:
        from weasyprint import HTML
        return HTML(string=html_content).write_pdf()
    except ImportError:
        raise ImportError("weasyprint 未安装,请执行 pip install weasyprint")
    except Exception as e:
        # 打印详细错误到 Streamlit Cloud 的日志
        print(f"PDF 生成失败: {type(e).__name__}: {e}")
        raise
```
然后在 Streamlit Cloud 的 Logs 页面查看具体报错信息。
