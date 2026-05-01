# AI 数据分析 Agent · 开发进度

## 今日完成（2026-05-01）

### Week 1 · Day 7：Schema 优化 + 确认机制预设计 [修订]

手册对应：`AI数据分析Agent_完整开发手册_v2.md` **第 260–312 行**

#### 修改文件

**`src/data_source.py`**

- **新增 `OLIST_RELATIONSHIPS`**：9 条表关系 SQL 注释，描述各表的 JOIN 键和一对多关系（如 orders → order_items / order_payments / order_reviews）
- **新增 `get_schema_with_relationships()`**：在 schema 文本开头附加表关系说明，供 NL2SQL prompt 使用，帮助 LLM 在多表查询时选对 JOIN 键
- **新增 `estimate_row_count(sql)`**：将原 SQL 包裹在 `COUNT(*)` 子查询中预估返回行数，失败返回 -1

**`src/app.py`**

- **新增 `should_confirm(sql, estimated_rows) -> bool`**：封装"是否需要用户确认"判断逻辑；当前 Week 1 阶段恒返回 True；Week 2 Day 10-11 只需改此函数（`estimated_rows > 100_000` → True，否则 → False），其余代码不动
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

## 当前停在

**Week 1 全部完成**，已具备：用中文提问 → LLM 生成 SQL → 确认卡片展示意图/表/行数 → 执行结果表格 → 历史记录可重放 → AI 自动修复报错 SQL。

手册进度：`AI数据分析Agent_完整开发手册_v2.md` **第 313 行**（Week 1 结束分割线），下次从 **第 314 行 `## 三、Week 2 · 升级为 Agent (Function Calling)`** 开始。

---

## 下次建议优先

**Week 2 · Day 8-9：理解 DeepSeek Function Calling**（手册第 314 行起）

具体方向：
1. **读手册第 314 行之后**，确认 Day 8-9 的具体任务和交付标准
2. **对话历史传给 LLM**：目前每次只发当轮问题，加入 `st.session_state.messages` 作多轮上下文，让 LLM 能理解"那 Top 5 呢？"之类的追问
3. **`should_confirm()` 升级**：改为 `estimated_rows > 100_000` 才弹确认，普通查询直接执行（手册 Week 2 Day 10-11 任务，但接口已预埋好）

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
