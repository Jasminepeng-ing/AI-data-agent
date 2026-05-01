"""
src/agent.py
============
Agent 主循环：基于 DeepSeek Function Calling 实现多步推理。

核心流程：
  1. 把 system prompt + 对话历史 + 用户消息组装成 messages
  2. 调用 LLM（带 tools 参数）
  3. LLM 返回 tool_calls → 解析 → 智能确认检查 → 执行 → 结果追加 messages → 继续
  4. LLM 返回最终文字回答（finish_reason=stop）→ 退出循环
  5. 超出 MAX_ITERATIONS → 强制退出，提示用户

智能确认规则（should_confirm）：
  - Week 1：return True（所有 SQL 都要人工确认）
  - Week 2：预估行数 > LARGE_QUERY_ROW_THRESHOLD（10万）才暂停确认
  - 接口已固定，Week 3 若需调整只改此函数
"""

import json
from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME, LARGE_QUERY_ROW_THRESHOLD
from tools import TOOLS_SCHEMA, execute_tool

MAX_ITERATIONS = 12

# Agent 的 system prompt：角色是会用工具的分析师，而非单纯 SQL 生成器
AGENT_SYSTEM_PROMPT = """\
你是一个专业的 AI 数据分析助手，通过调用工具完成数据查询、可视化和统计分析任务。

【可用工具】
1. query_database  — 执行 SQL 查询获取数据（必须先于 make_chart / analyze_dataframe 调用）
2. make_chart      — 对已查询的数据绘制图表（bar/line/pie/scatter）
3. analyze_dataframe — 对已查询的数据做统计分析（describe/correlation/groupby_summary）

【数据库结构】
{schema_text}

【SQL 编写规则（query_database 必须遵守）】
1. 只允许 SELECT 语句，严禁 INSERT/UPDATE/DELETE/DROP/CREATE 等写操作。
2. 使用 DuckDB 兼容语法，表名和字段名必须用双引号，如 "orders"."order_id"。
3. 优先使用 LEFT JOIN，避免 INNER JOIN 因附属表缺记录而静默丢行。
4. 多个一对多关系表（如 order_items 和 order_payments 都与 orders 是一对多）
   严禁直接三表 JOIN（会导致笛卡尔积膨胀，SUM/COUNT 虚高）。
   正确做法：用 WITH 子句或子查询先对各一对多表单独聚合到订单粒度，再 LEFT JOIN 主表。
5. LEFT JOIN 后 COUNT 用 COUNT(附属表的字段)，不用 COUNT(*)（后者会把无匹配的 NULL 行也计入）。
6. 不得添加用户未明确要求的 WHERE 过滤条件。
7. 用户说的"X 中…"是分组维度，不是过滤条件，不得因此加 WHERE。

【工作方式】
- 分析用户需求，规划工具调用顺序（查询 → 可选绘图 / 分析），按顺序调用。
- 所有工具调用完成后，用中文向用户解释结果，提供数据洞察和建议。
- 如果问题不涉及数据查询，直接用文字回答，不要强行调工具。
- 工具执行失败时，分析错误原因，用修正后的参数重试（最多重试 2 次）。
"""


def should_confirm(sql: str, estimated_rows: int) -> bool:
    """
    智能确认：是否需要暂停 Agent 并请用户手动确认再执行此 SQL。

    Week 1 逻辑：return True（所有查询都要确认）
    Week 2 逻辑：仅当预估行数超过阈值（10万）才需要确认，普通查询直接执行。

    estimated_rows = -1 表示预估失败，保守起见也直接执行（-1 < 阈值）。
    """
    return estimated_rows > LARGE_QUERY_ROW_THRESHOLD


def run_agent(
    user_message: str,
    history: list,
    ds,
    status_container=None,
) -> dict:
    """
    Agent 主循环。

    Parameters
    ----------
    user_message : str
        用户当前输入的问题。
    history : list
        st.session_state.messages（不含本轮 user message），用于多轮上下文。
    ds : DataSource
        数据源，传给 execute_tool 内部的工具函数使用。
    status_container : streamlit container（可选）
        传入 st.status() 返回的对象，用于实时展示工具调用进度。
        若为 None，则静默执行（不更新 UI）。

    Returns
    -------
    dict
        {
            "final_answer"  : str,   # LLM 的最终文字回答（空字符串表示被 needs_confirm 打断）
            "tool_calls_log": list,  # [{tool_name, args, result}, ...]，记录所有已执行工具
            "needs_confirm" : dict | None,
                # 非 None 时表示检测到大数据量查询，需要用户先确认：
                # {question, sql, intent, estimated_rows}
        }
    """
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    schema_text = ds.get_schema_with_relationships()
    system_content = AGENT_SYSTEM_PROMPT.format(schema_text=schema_text)

    # ── 构建 messages ───────────────────────────────────────────────────────
    messages = [{"role": "system", "content": system_content}]

    # 对话历史：只取 role/content，剥离 dataframe/charts 等 UI 专用字段
    for msg in history:
        if msg["role"] not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        if not content:
            continue
        messages.append({"role": msg["role"], "content": content})

    messages.append({"role": "user", "content": user_message})

    tool_calls_log: list[dict] = []

    for iteration in range(MAX_ITERATIONS):
        # ── 调用 LLM ────────────────────────────────────────────────────────
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.3,
            )
        except Exception as e:
            return {
                "final_answer":   f"⚠️ 调用 AI 失败：{e}",
                "tool_calls_log": tool_calls_log,
                "needs_confirm":  None,
            }

        choice      = response.choices[0]
        llm_message = choice.message
        finish_reason = choice.finish_reason

        # DeepSeek 偶发假 tool_calls（字段存在但内容为 None 或空列表）
        has_tool_calls = bool(llm_message.tool_calls)

        if not has_tool_calls or finish_reason == "stop":
            return {
                "final_answer":   llm_message.content or "",
                "tool_calls_log": tool_calls_log,
                "needs_confirm":  None,
            }

        # ── 处理本轮所有 tool_calls ─────────────────────────────────────────
        messages.append(llm_message)  # 把含 tool_calls 的 assistant message 加入历史

        for tool_call in llm_message.tool_calls:
            tool_name = tool_call.function.name

            # 参数 JSON 解析（DeepSeek 偶发非法 JSON，必须容错）
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                err_msg = "参数 JSON 解析失败，请检查参数格式后重试"
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "content":      err_msg,
                })
                tool_calls_log.append({"tool_name": tool_name, "args": {}, "result": err_msg})
                continue

            # 智能确认：query_database 预估行数超过阈值时，暂停等用户确认
            if tool_name == "query_database":
                sql = args.get("sql", "")
                estimated_rows = ds.estimate_row_count(sql)
                if should_confirm(sql, estimated_rows):
                    return {
                        "final_answer":   "",
                        "tool_calls_log": tool_calls_log,
                        "needs_confirm":  {
                            "question":       user_message,
                            "sql":            sql,
                            "intent":         args.get("intent", "大数据量查询"),
                            "estimated_rows": estimated_rows,
                        },
                    }

            # 实时进度展示
            intent_hint = (
                args.get("intent")
                or args.get("title")
                or args.get("analysis_type")
                or tool_name
            )
            if status_container:
                status_container.write(f"🔧 调用工具: **{tool_name}** — {intent_hint}")

            # 执行工具
            tool_result = execute_tool(tool_name, args, ds)

            tool_calls_log.append({
                "tool_name": tool_name,
                "args":      args,
                "result":    tool_result,
            })

            messages.append({
                "role":         "tool",
                "tool_call_id": tool_call.id,
                "content":      str(tool_result),
            })

    # 超出最大迭代次数（防无限循环）
    return {
        "final_answer":   "⚠️ Agent 超出最大工具调用次数（12次），请换一个更具体的问题重试。",
        "tool_calls_log": tool_calls_log,
        "needs_confirm":  None,
    }
