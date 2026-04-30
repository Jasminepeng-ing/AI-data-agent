# AI 数据分析 Agent · 开发进度

## 今日完成（2026-04-30）

### Week 2 · Day 5-6：接通 DeepSeek 实现 NL2SQL

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
- 新增 `pending` 状态机（存于 `session_state`），实现跨 rerun 的多步交互流程：
  - `confirm`：展示 LLM 生成的 SQL + [确认执行] [取消]
  - `error`：展示报错信息 + [让 AI 修复] [取消]
- 新增 `_render_message()`：渲染历史消息，支持附带 SQL 折叠块和 DataFrame 结果表格
- 新增 `_render_pending()`：渲染待确认 / 待修复区块
- `render_chat()` 重构：历史渲染 → pending 区块 → 输入框，三段清晰分离

#### 问题修复

| 问题 | 根因 | 解法 |
|---|---|---|
| `No module named 'openai'` | `.venv` 环境缺依赖 | `pip install openai python-dotenv` |
| LLM 丢失 installments=0/1 的行 | 把"分期付款中"解读为 `WHERE > 1` | system prompt 加第 6-8 条禁止隐式过滤；user prompt 末尾加强提醒；`temperature` 降为 0 |

---

## 当前停在

**NL2SQL 核心流程已跑通**，用户可以：
1. 用自然语言提问
2. 查看 LLM 生成的 SQL
3. 确认执行并看到结果表格
4. SQL 出错时一键让 AI 修复

手册进度：`AI数据分析Agent_完整开发手册_v2.md` **第 248 行**（Week 2 · Day 5-6 任务全部完成）。

---

## 明天建议优先

按手册顺序，下一阶段为 **Week 2 后半段 / Week 3**，建议按以下顺序推进：

1. **读手册下一节**：确认下一个任务区间（第 249 行之后）的具体要求
2. **对话历史传给 LLM**：目前每次调用只发当轮问题，加入 `st.session_state.messages` 作为多轮上下文，让 LLM 能理解追问
3. **大查询行数确认**：`LARGE_QUERY_ROW_THRESHOLD = 100_000` 已定义，补上超阈值时弹二次确认的交互逻辑
4. **结果可视化**：在 `st.dataframe` 之后，根据结果列类型自动推荐并渲染 `st.bar_chart` / `st.line_chart`
