"""TODO Tracker — 响应式子 Agent，自动追踪任务步骤进度.

替代 LangChain 内置 TodoListMiddleware:
- Simple 模式（无 tools，直接 LLM 调用）
- 每次主 LLM 输出后自动触发
- context_builder 提取精简上下文（≤500 tokens）
- result_parser 解析 JSON 输出为 todos state 更新
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.subagents.types import ReactiveSubAgentConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 系统提示词
# ---------------------------------------------------------------------------

TODO_SYSTEM_PROMPT = """\
你是任务进度跟踪器。你的唯一职责是根据 Agent 的当前活动，输出任务步骤列表。

## 输出格式

输出**纯 JSON 数组**，不要包含任何其他文字、markdown 标记或解释。

每个元素格式:
{"content": "步骤描述", "status": "pending|in_progress|completed"}

## 状态规则

- pending: 尚未开始的步骤
- in_progress: 正在执行中的步骤（工具正在被调用）
- completed: 已完成的步骤（工具已返回结果）

## 推断规则

1. 如果 Agent 正在调用工具 → 对应步骤标记为 in_progress
2. 如果工具已返回结果 → 对应步骤标记为 completed
3. 如果 Agent 输出最终回复（无工具调用）→ 所有已执行的步骤标记为 completed
4. 步骤数量保持在 3-6 个，覆盖完整分析流程
5. 保留已有步骤描述，只更新状态
6. 步骤描述使用简洁中文

## 典型步骤模板

- 检索领域知识和术语定义
- 匹配仿真场景
- 执行根因分析
- 展示分析结果
- 执行优化仿真
- 对比优化前后结果
"""


# ---------------------------------------------------------------------------
# Context Builder
# ---------------------------------------------------------------------------

def build_todo_context(state: dict[str, Any]) -> list[HumanMessage] | None:
    """从 parent state 提取精简上下文供 TODO 子 Agent 使用.

    提取内容:
    - 最近的用户任务描述（≤300 字符）
    - 当前 TODO 步骤状态
    - 最近 AI 操作摘要（工具调用名 + 结果状态）
    """
    messages = state.get("messages", [])
    if not messages:
        return None

    current_todos = state.get("todos", [])

    # 查找最近的用户消息
    user_task = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) or (
            hasattr(msg, "type") and getattr(msg, "type", None) == "human"
        ):
            content = msg.content if hasattr(msg, "content") else str(msg)
            user_task = content[:300] if isinstance(content, str) else str(content)[:300]
            break

    if not user_task:
        return None

    # 提取最近操作（最后 8 条消息）
    recent_actions: list[str] = []
    for msg in messages[-8:]:
        if isinstance(msg, AIMessage):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                names = [tc.get("name", "?") for tc in msg.tool_calls]
                recent_actions.append(f"[调用工具] {', '.join(names)}")
            elif msg.content:
                text = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(text) > 150:
                    text = text[:150] + "..."
                recent_actions.append(f"[AI回复] {text}")
        elif isinstance(msg, ToolMessage):
            name = getattr(msg, "name", "?")
            status = "失败" if getattr(msg, "status", None) == "error" else "成功"
            recent_actions.append(f"[工具结果] {name}: {status}")

    # 组装上下文
    parts = [f"用户任务: {user_task}"]

    if current_todos:
        todos_lines = "\n".join(
            f"- [{t.get('status', 'pending')}] {t.get('content', '')}"
            for t in current_todos
        )
        parts.append(f"当前步骤:\n{todos_lines}")
    else:
        parts.append("当前没有任务步骤，请根据 Agent 活动创建初始步骤。")

    if recent_actions:
        parts.append("最近操作:\n" + "\n".join(recent_actions))

    context = "\n\n".join(parts)
    return [HumanMessage(content=context)]


# ---------------------------------------------------------------------------
# Result Parser
# ---------------------------------------------------------------------------

def parse_todo_result(raw_output: str) -> dict[str, Any] | None:
    """解析 LLM JSON 输出为 {"todos": [...]}.

    支持:
    - 纯 JSON 数组
    - 被 markdown 代码块包裹的 JSON
    """
    if not raw_output or not isinstance(raw_output, str):
        return None

    content = raw_output.strip()

    # 去除 markdown 代码块标记
    if content.startswith("```"):
        lines = content.split("\n")
        # 去掉首行 ``` 或 ```json
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        # 去掉尾行 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning(
            f"todo_tracker: JSON 解析失败, content={content[:200]}"
        )
        return None

    if not isinstance(data, list):
        return None

    # 规范化
    normalized: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        c = str(item.get("content", "")).strip()
        s = str(item.get("status", "pending")).strip()
        if not c:
            continue
        if s not in ("pending", "in_progress", "completed"):
            s = "pending"
        normalized.append({"content": c, "status": s})

    return {"todos": normalized} if normalized else None


# ---------------------------------------------------------------------------
# Trigger Condition
# ---------------------------------------------------------------------------

def should_fire(state: dict[str, Any]) -> bool:
    """仅当最后一条消息是 AIMessage 时触发.

    跳过 ToolMessage 等非 AI 输出，避免不必要的子 Agent 调用。
    """
    messages = state.get("messages", [])
    if not messages:
        return False
    last = messages[-1]
    return isinstance(last, AIMessage)


# ---------------------------------------------------------------------------
# 配置导出
# ---------------------------------------------------------------------------

TODO_TRACKER_CONFIG: ReactiveSubAgentConfig = {
    "name": "todo_tracker",
    "description": "自动追踪和更新任务步骤进度",
    "system_prompt": TODO_SYSTEM_PROMPT,
    # 无 tools → Simple 模式
    "trigger_hook": "after_model",
    "trigger_condition": should_fire,
    "context_builder": build_todo_context,
    "result_parser": parse_todo_result,
    "owned_state_keys": ["todos"],
    "fallback_on_error": {},
}
