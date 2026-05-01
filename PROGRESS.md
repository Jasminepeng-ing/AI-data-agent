# AI 数据分析 Agent · 开发进度

## 今日完成（2026-05-02）

### 数据一致性深度排查 · Prompt 防护体系完善（无手册对应，超出计划的自主 QA）

本次工作以实际提问测试 Agent 输出质量为驱动，发现并修复了 5 个层叠 bug，最终建立了一套防止 LLM 产生幻觉数据的系统性防护规则。

#### 问题背景

以"2017年Q4哪10品类销售额下跌最严重"为测试题，反复与 Agent 输出对比，逐步挖出根因。

---

#### Bug 1：LLM 返回结果只预览 3 行，排名 4-10 靠幻觉填充

**现象**：Agent 输出的 Top 3 正确，第 4-10 名全部是捏造的品类和数字（furniture_decor、garden_tools 等实际上 Q4 是上涨的）。

**根因**：`tools.py` 的 `query_database()` 仅返回 `df.head(3)` 给 LLM。SQL 查出 10 行，LLM 只看到 3 行，对剩余 7 行凭印象填充。

**修复（`src/tools.py`）**：改为**动态截断策略**：
- 结果 ≤ 100 行 → 全量传给 LLM（零幻觉）
- 结果 > 100 行 → 只传前 100 行 + `⚠️` 截断警告，提示 LLM 加 LIMIT

```python
MAX_FULL_ROWS = 100
if len(df) <= MAX_FULL_ROWS:
    data_text = df.to_string(index=False)   # 全量
else:
    data_text = df.head(MAX_FULL_ROWS).to_string(index=False)
    suffix = f"⚠️ 结果共 {len(df)} 行，已截断至前 {MAX_FULL_ROWS} 行..."
```

**配套（`src/agent.py` 工作方式）**：新增【数据完整性】规则，明确 LLM 看到的就是完整数据，禁止在结果之外补充任何行或数字。

---

#### Bug 2：LLM 自行添加 `order_status != 'canceled'` 隐式过滤

**现象**：每个 SQL 都包含 `AND o."order_status" != 'canceled'`，用户从未要求。

**根因**：违反 System Prompt 规则 6（禁止隐式过滤），LLM 自以为"分析销售额当然要排除取消订单"。

**修复**：
- `src/agent.py` 规则 6 补充：**严禁自行加 `order_status != 'canceled'`**，未经要求必须查全量
- `src/prompts.py` 规则 6 补充反例

---

#### Bug 3：products 表有 610 个产品无品类（NULL），混入品类排名

**现象**：排名中出现 `None（未分类）`，环比跌幅 -100%，跌幅金额 -14,272，占据一个席位挤掉真实品类。

**根因**：`products.product_category_name` 有 610 条 NULL，`COALESCE(t.english, p.name)` 结果仍为 NULL，被 pandas 渲染为 `"None"` 并混入排名。

**隐藏的次生 Bug**：FULL OUTER JOIN 中 `NULL = NULL` 在 SQL 里判为 **False**，导致 Q3 和 Q4 的 NULL 品类行无法配对：Q3 NULL 行独立显示为 Q4=0（实际 Q4 有 49,141 销售额），虚假跌幅 -100%。

**修复（`src/agent.py` 规则 10 + `src/prompts.py` 规则 13）**：品类分析 SQL 必须在每个 CTE 加：
```sql
WHERE p."product_category_name" IS NOT NULL
```

---

#### Bug 4：品类自造标签（CASE WHEN / LIKE 合并多个葡文品类）

**现象**：fashio_female_clothing 的 Q3 销售额从正确的 855 虚增到 6,758（约 8 倍）。

**根因**：LLM 用 `CASE WHEN product_category_name LIKE '%roupa%'` 创造了假标签 `'fashio_feminine'`，把女装、男装、童装等多个葡文品类错误合并。

**修复**（已在前次对话中实施）：
- `src/agent.py` 规则 9：必须 JOIN 翻译表，严禁 CASE WHEN / LIKE 伪造品类名
- `src/prompts.py` 规则 12：同上

---

#### Bug 5（自查发现）：我自己给出的"标准答案"环比跌幅 Top 10 有误

**现象**：我给出的环比跌幅 Top 10 遗漏了 `arts_and_craftmanship`、`security_and_services`、`music`、`fashion_childrens_clothes`（这 4 个品类真实跌幅均 ≥ -71%）。

**根因**：我的验证 SQL 先按**绝对跌幅** `LIMIT 15`，再从该子集按百分比重排。上述 4 个品类绝对金额小（-130、-100、-274、-100），未进 LIMIT 15，被错误排除。

**正确的环比跌幅 Top 10**（已修正，可作为后续对照基准）：

| 排名 | 品类 | Q3 | Q4 | 环比跌幅 |
|:---:|---|---:|---:|---:|
| 1 | small_appliances_home_oven_and_coffee | 750.05 | 0.00 | -100% |
| 2 | arts_and_craftmanship | 129.90 | 0.00 | -100% |
| 3 | security_and_services | 100.00 | 0.00 | -100% |
| 4 | fashio_female_clothing | 855.10 | 79.88 | -90.66% |
| 5 | music | 329.00 | 54.90 | -83.31% |
| 6 | fashion_sport | 720.30 | 179.70 | -75.05% |
| 7 | fashion_childrens_clothes | 139.89 | 39.99 | -71.41% |
| 8 | fixed_telephony | 17,255.18 | 5,694.63 | -67.00% |
| 9 | la_cuisine | 782.99 | 274.00 | -65.01% |
| 10 | dvds_blu_ray | 902.90 | 394.19 | -56.34% |

---

#### 修改文件汇总

| 文件 | 变更内容 |
|---|---|
| `src/tools.py` | `query_database()` 预览策略：≤100行全量，>100行截断+警告（原来只传3行） |
| `src/agent.py` | 规则6补充 canceled 过滤禁令；规则10新增 NULL 品类过滤要求；工作方式新增【数据完整性】 |
| `src/prompts.py` | 规则6补充 canceled 反例；规则13新增 NULL 品类过滤要求 |

---

## 当前停在

**Week 2 · Day 12-13 完成 + 数据一致性专项 QA 完成**

当前 Agent 具备的防护规则（`src/agent.py` SQL 规则 1-10）：
1. 只允许 SELECT
2. DuckDB 语法 + 双引号字段名
3. 优先 LEFT JOIN
4. 禁止多个一对多表直接 JOIN（Fan-out）
5. LEFT JOIN 后 COUNT 用字段而非 *
6. 禁止隐式过滤（含 canceled、状态过滤）
7. "X 中…"是分组维度，不是 WHERE
8. 增跌排名默认用百分比
9. 禁止自造品类标签（必须 JOIN 翻译表）
10. **[新增]** 必须过滤 NULL 品类（`product_category_name IS NOT NULL`）

手册进度：`AI数据分析Agent_完整开发手册_v2.md` 第 588 行（Day 12-13 结束）。
下次从 **Day 14：多轮记忆 + 上下文管理** 开始（手册第 589 行起）。

---

## 历史记录（2026-05-01）

### Week 2 · Day 12-13：多步分析能力

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 545–588 行**

#### 修改文件

**`src/agent.py`**

- **`AGENT_SYSTEM_PROMPT` 新增【多步分析规划】章节**，包含 4 条强制规则：
  1. 先输出纯文字分析计划（格式：`"分析计划：我将分 N 步完成这个分析：第1步…"`），不调工具
  2. 逐步调用工具，`intent` 参数与计划步骤描述一致
  3. 每步完成后用 1-2 句说明发现（下次 LLM 回复输出）
  4. 全部完成后综合结论
  以及 `make_chart` 前必须确认数据已查、对比图需两组数据都查完、必须显式传 `result_key`
- **`run_agent()` 加 `step_count` 步骤计数器**：在 `tool_calls_log` 每条记录里增加 `step` 字段（全局递增，跨 iteration 不重置）；status 显示从 `"🔧 调用工具: ..."` 升级为 `"第 N 步 🔧 \`tool_name\` — intent"`

**`src/app.py`**

- **`_render_message()` 折叠块标签加步骤号**：`f"第 {step_num} 步 🔧 {tool_name}: {intent_hint}"`，兼容旧消息（无 `step` 字段时用枚举序号 `i` 回退）
- **status 初始提示更新**：`"📖 读取问题，制定分析计划…"`（体现多步规划语义）

#### 交付标准对应

| 手册测试场景 | 预期 Agent 行为 |
|---|---|
| `"2017年总销售额"` | 1步：query_database → 直接给结论 |
| `"Top 10 销售品类"` | 2步：query_database（带 intent）→ make_chart（指定 result_key）→ 结论 |
| `"Q4 vs Q3 各品类对比"` | 多步：先输出分析计划 → query Q3 → query Q4 → analyze / make_chart → 综合结论 |

---

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
