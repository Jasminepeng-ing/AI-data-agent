# AI 数据分析 Agent · 开发进度

## 今日完成（2026-05-01）

### Week 2 · Day 10-11：重构成 Agent 架构

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 336–542 行**

#### 新建文件

**`src/tools.py`**

- **`TOOLS_SCHEMA`**：3 个工具的 Function Calling JSON Schema 定义
- **`query_database(sql, intent, ds)`**：执行 SQL，结果存入 `session_state['query_results'][intent]`（带 df/sql/timestamp/row_count/columns），返回给 LLM 的是文字摘要（行数+列名+前3行），不传完整 DataFrame
- **`make_chart(chart_type, x_col, y_col, title, result_key, ds)`**：Plotly Express 绘图，Figure 存入 `session_state['_agent_charts']`，由 app.py 在 Agent 返回后统一渲染（确保历史消息图表可回放）
- **`analyze_dataframe(analysis_type, result_key)`**：describe / correlation / groupby_summary 三种统计分析，返回文字描述
- **`execute_tool(name, args, ds)`**：统一调度器，agent.py 只调这一个函数

**`src/agent.py`**

- **`AGENT_SYSTEM_PROMPT`**：Agent 专用 system prompt，包含工具说明 + 数据库结构占位符 + SQL 规则 + 工作方式，与 NL2SQL prompt 完全独立
- **`should_confirm(sql, estimated_rows) -> bool`**：智能确认（Week 2）：`estimated_rows > 100_000` 才返回 True；Week 1 是 `return True`
- **`run_agent(user_message, history, ds, status_container) -> dict`**：Agent 主循环
  - 组装 messages（system + 历史 + 当前问题）
  - 带 `tools=TOOLS_SCHEMA, tool_choice="auto", temperature=0.3` 调用 DeepSeek
  - 检测假 tool_calls（DeepSeek 偶发 None/空列表）
  - JSON 解析容错（json.JSONDecodeError → 返回错误消息给 LLM）
  - 智能确认检查（大查询暂停，返回 `needs_confirm` dict）
  - 实时进度：通过 `status_container.write()` 展示每步工具调用
  - 最大迭代次数 `MAX_ITERATIONS = 12`
  - 返回 `{final_answer, tool_calls_log, needs_confirm}`

#### 修改文件

**`src/app.py`**

- **移除旧 `call_llm()`**：替换为 `call_llm_for_fix()`，仅用于大查询确认执行报错时的 AI 修复，正常流程通过 `run_agent()` 处理
- **移除 `should_confirm()`**：逻辑迁移至 `agent.py`，Week 2 版本（`> 10万`）
- **`init_session_state()` 新增**：`query_results = {}`、`latest_query_key = None`、`_agent_charts = []`
- **`_render_message()` 增强**：渲染 `tool_calls_log`（每个工具调用展示为折叠 expander，含 SQL 预览和结果摘要）+ `charts`（Plotly 图表）；保留 Week 1 的 `sql` 字段兼容
- **`_render_pending()` 修订**：confirm 状态改为"大数据量确认"语义，确认后同时写入 `query_results`（供后续工具引用）；error 状态保持不变
- **新增 `_run_and_store_agent()`**：统一的 Agent 调用+结果存储函数，`render_chat` 和历史回放共用，避免代码重复
- **`render_chat()` 重构**：用户输入 → `st.status()` 实时展示进度 → `run_agent()` → 结果写入 messages → `st.rerun()`
- **Sidebar 新增"本轮已执行查询"区块**：展示 `query_results` 条目（倒序）、📋 查看 SQL、**↩️ 撤销上一步查询**按钮（删除最后一条 query_result + 最后一条 assistant 消息）
- **侧边栏历史回放改进**：▶ 按钮通过 `_replay_question` session_state key 触发 Agent 完整流程，而非直接进入 pending 状态

#### 架构决策说明

| 决策 | 原因 |
|---|---|
| `make_chart` 把 Figure 存入 `_agent_charts` 而非直接渲染 | Agent 在 `st.status()` 上下文内运行，直接调 `st.plotly_chart()` 会渲染在错误位置；统一由 app.py 渲染确保历史回放正常 |
| `should_confirm` 放在 `agent.py` 而非 `app.py` | 确认逻辑是 Agent 执行策略的一部分，与 LLM 调用紧耦合 |
| 大查询确认后不自动继续 Agent 循环 | 需要保存完整 messages 快照才能恢复，Week 2 简化处理；Week 3 可扩展 |
| `call_llm_for_fix` 保留独立 NL2SQL 修复路径 | 大查询确认后若执行失败，用简单 NL2SQL 修复比重启 Agent 循环更可预期 |

---

## 当前停在

**Week 2 · Day 10-11 完成**，已具备：
- 用户提问 → Agent 自动规划工具调用（NL2SQL + 画图 + 统计分析）
- 实时展示 Agent 思考进度（`st.status()` 面板）
- 小查询（< 10 万行）直接执行，大查询才弹确认框
- 侧边栏展示本轮已执行查询 + 撤销上一步
- 多轮对话历史传给 LLM（追问功能）

手册进度：`AI数据分析Agent_完整开发手册_v2.md` 第 542 行（Day 10-11 结束）。
下次从 **Day 12-14** 开始（手册第 543 行起）。

---

## 历史记录（2026-05-01 上午）

### Week 2 · Day 8-9：理解 DeepSeek Function Calling

无代码改动，学习阶段，掌握以下概念：
- Function Calling vs 普通 API 调用的区别（军师 vs 执行者模型）
- Agent 循环流程（messages → LLM → tool_calls → 执行 → 追加结果 → 继续）
- tools 参数 JSON Schema 写法
- tool_call_id 必须原值回传
- Parallel tool calls 处理方式
- DeepSeek 特有坑（假 tool_calls、JSON 非法、温度建议 0.3-0.5）

---

## 历史记录（2026-05-01 凌晨）

### Week 1 · Day 7：Schema 优化 + 确认机制预设计 [修订]

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 260–312 行**

#### 修改文件

**`src/data_source.py`**

- **新增 `OLIST_RELATIONSHIPS`**：9 条表关系 SQL 注释，描述各表的 JOIN 键和一对多关系（如 orders → order_items / order_payments / order_reviews）
- **新增 `get_schema_with_relationships()`**：在 schema 文本开头附加表关系说明，供 NL2SQL prompt 使用，帮助 LLM 在多表查询时选对 JOIN 键
- **新增 `estimate_row_count(sql)`**：将原 SQL 包裹在 `COUNT(*)` 子查询中预估返回行数，失败返回 -1

**`src/app.py`**

- **新增 `should_confirm(sql, estimated_rows) -> bool`**：封装"是否需要用户确认"判断逻辑；Week 1 阶段恒返回 True；Week 2 Day 10-11 已升级为智能判断（`> 10万` 才确认）
- **新增 `_parse_sql_meta(sql)`**：用正则提取涉及表名和是否含 JOIN，供确认卡片展示元信息
- **SQL 确认卡片改进**：在 SQL 预览前新增三列元信息卡片 —— 查询意图（中文）、涉及表名列表、是否含 JOIN、预估行数
- **新增侧边栏 SQL 历史**：`sql_history` 存入 `session_state`，最多保留 10 条（去重），每条附 ▶ 按钮可重新执行
- **`_render_message()` 增强**：message dict 新增 `question` 字段；历史渲染时在"查询完成"前用 `st.caption` 显示原始问题，方便历史回放时识别上下文

#### 超出手册的自主优化

**`src/app.py`**

- **新增 `_render_dataframe_with_total()`**：合计行拼接在主表末尾并高亮，单表渲染，下载时一并导出
- **新增 `_is_amount_col()` + `_AMOUNT_KEYWORDS`**：按列名关键词识别金额列（英/葡/中文），金额浮点列启用千位符 + 2 位小数，普通浮点列保留 2 位小数，金额整数列启用千位符

**`src/prompts.py`**

在 `NL2SQL_SYSTEM_PROMPT` 中新增 3 条硬性约束，解决多表查询数据不一致问题：

| 约束编号 | 内容摘要 | 解决的问题 |
|---|---|---|
| 9 | **优先使用 LEFT JOIN**，附属表必须用 LEFT JOIN，链式多表每个附属表单独评估 | INNER JOIN 静默丢行（如 SP 州 41,746 → 41,745）|
| 10 | **禁止多个一对多表直接 JOIN（Fan-out）**，必须先用 WITH/子查询分别聚合再 JOIN | 笛卡尔积膨胀导致 SUM/COUNT 虚高 |
| 11 | **NULL 与聚合函数一致性**：LEFT JOIN 后 `COUNT(*)` 改为 `COUNT(字段)`，必要时用 `COALESCE` 补零 | `COUNT(*)` 把无匹配行也计入统计 |

#### Bug 修复

| 问题 | 根因 | 解法 |
|---|---|---|
| `ValueError: Cannot specify ',' with 's'` | 合计行第一列为字符串 `"合计"`，concat 后列 dtype → object；列名含 `payment` 被识别为金额列，格式字符串 `{:,}` 作用于字符串值报错 | 改用 callable lambda formatter，`isinstance` 类型检查，非数值直接 `str(x)` 返回 |
| 历史回放时看不出查询的是什么问题 | message 存储时未保存 `question` 字段，渲染时无从展示 | message dict 新增 `question`；`_render_message()` 在内容前 `st.caption` 展示原始问题 |

---

## 历史记录（2026-04-30）

### Week 1 · Day 5-6：接通 DeepSeek 实现 NL2SQL

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 200–258 行**

#### 新建文件

**`src/config.py`**
- 从 `.env` 读取 `DEEPSEEK_API_KEY`
- 定义 LLM 相关常量：`DEEPSEEK_BASE_URL`、`MODEL_NAME`、`MAX_TOKENS`、`LARGE_QUERY_ROW_THRESHOLD`

**`src/prompts.py`**
- 定义 `NL2SQL_SYSTEM_PROMPT`：角色、任务、8 条硬性约束（含禁止隐式过滤）
- `build_nl2sql_prompt(user_question, schema_text)`：动态拼接 user prompt，末尾附"生成 SQL 前必读"强提醒
- `build_fix_prompt(...)`：SQL 执行报错时，将错误信息 + 原 SQL 发给 LLM 请求修复

#### 修改文件

**`src/app.py`**
- 新增 `call_llm(user_prompt)`：调用 DeepSeek API，`temperature=0` 保证确定性
- 新增 `pending` 状态机（存于 `session_state`），实现跨 rerun 的多步交互流程
- 新增 `_render_message()`：渲染历史消息，支持附带 SQL 折叠块和 DataFrame 结果表格
- 新增 `_render_pending()`：渲染待确认 / 待修复区块
- `render_chat()` 重构：历史渲染 → pending 区块 → 输入框，三段清晰分离

#### 问题修复

| 问题 | 根因 | 解法 |
|---|---|---|
| `No module named 'openai'` | `.venv` 环境缺依赖 | `pip install openai python-dotenv` |
| LLM 丢失 installments=0/1 的行 | 把"分期付款中"解读为 `WHERE > 1` | system prompt 加第 6-8 条禁止隐式过滤；`temperature` 降为 0 |
