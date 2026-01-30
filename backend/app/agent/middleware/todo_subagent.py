"""Todo Sub-Agent Middleware - independent LLM for automatic task progress tracking.

Replaces the standard TodoListMiddleware which relies on the main agent
voluntarily calling write_todos. In multi-turn conversations with many tools
and large context, the main agent often "forgets" to update todos.

This middleware uses a dedicated lightweight LLM with minimal context to
automatically analyze agent actions and update todo state after each model turn.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from typing_extensions import NotRequired, TypedDict, override

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    OmitFromInput,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langgraph.runtime import Runtime

    from langchain.agents.middleware.types import (
        ModelCallResult,
        ModelRequest,
        ModelResponse,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State schema (same shape as TodoListMiddleware's PlanningState)
# ---------------------------------------------------------------------------

class Todo(TypedDict):
    """A single todo item."""

    content: str
    status: Literal["pending", "in_progress", "completed"]


class TodoSubAgentState(AgentState[Any]):
    """State schema adding todos field."""

    todos: Annotated[NotRequired[list[Todo]], OmitFromInput]


# ---------------------------------------------------------------------------
# Sub-agent system prompt (kept minimal for speed)
# ---------------------------------------------------------------------------

_SUB_AGENT_SYSTEM = """\
你是一个任务进度追踪助手。你的职责是根据Agent的操作自动维护任务列表。

规则：
1. 如果没有现有任务，根据用户请求创建 3-6 个任务步骤
2. 如果Agent正在调用工具，将对应任务标记为 in_progress
3. 如果工具调用已完成（上一轮有结果），将对应任务标记为 completed
4. 如果Agent给出了最终回复（无工具调用），将所有已执行的任务标记为 completed
5. 保持任务描述简洁（10字以内）
6. 不要删除已有任务，只更新状态
7. 可以在发现新需求时追加任务

只输出 JSON 数组，不要输出任何其他内容。格式：
[{"content": "任务描述", "status": "pending|in_progress|completed"}]"""

# Injected into the main agent's system prompt so it knows progress is tracked
_MAIN_AGENT_ADDON = """\

## 任务进度

系统会自动跟踪你的任务执行进度，你不需要手动管理任务列表。专注于执行用户请求即可。"""


class TodoSubAgentMiddleware(AgentMiddleware):
    """Middleware that uses an independent lightweight LLM to manage todos.

    Unlike ``TodoListMiddleware`` which adds a ``write_todos`` tool for the
    main agent to call voluntarily, this middleware:

    * Has its own dedicated LLM instance (can be a smaller/cheaper model)
    * Fires automatically after every model turn via ``after_model``
    * Keeps minimal context (only user request + current todos + latest action)
    * Never competes with domain tools for the main agent's attention

    This ensures todo progress updates reliably even in long multi-turn
    conversations with heavy context.
    """

    state_schema = TodoSubAgentState

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0,
        max_tokens: int = 512,
    ) -> None:
        super().__init__()
        # Import settings lazily to avoid circular imports
        from app.config import settings

        resolved_model = (
            model
            or settings.todo_agent_model
            or settings.llm_model  # fallback to main model if not configured
        )
        self._llm = ChatOpenAI(
            model=resolved_model,
            openai_api_key=api_key or settings.llm_api_key,
            openai_api_base=base_url or settings.llm_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=False,  # No need to stream the sub-agent's output
        )

    # ------------------------------------------------------------------
    # wrap_model_call: inject a brief note so the main agent knows
    # progress tracking is automatic (and can focus on its real job)
    # ------------------------------------------------------------------

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        if request.system_message is not None:
            new_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": _MAIN_AGENT_ADDON},
            ]
        else:
            new_content = [{"type": "text", "text": _MAIN_AGENT_ADDON}]
        new_sys = SystemMessage(content=cast("list[str | dict[str, str]]", new_content))
        return handler(request.override(system_message=new_sys))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        if request.system_message is not None:
            new_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": _MAIN_AGENT_ADDON},
            ]
        else:
            new_content = [{"type": "text", "text": _MAIN_AGENT_ADDON}]
        new_sys = SystemMessage(content=cast("list[str | dict[str, str]]", new_content))
        return await handler(request.override(system_message=new_sys))

    # ------------------------------------------------------------------
    # after_model: invoke sub-agent to update todos
    # ------------------------------------------------------------------

    @override
    def after_model(
        self, state: AgentState[Any], runtime: Runtime
    ) -> dict[str, Any] | None:
        return self._do_update(state)

    @override
    async def aafter_model(
        self, state: AgentState[Any], runtime: Runtime
    ) -> dict[str, Any] | None:
        return self._do_update(state)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_update(self, state: AgentState[Any]) -> dict[str, Any] | None:
        """Core logic: build a minimal prompt and call the sub-agent LLM."""
        messages = state.get("messages", [])
        if not messages:
            return None

        current_todos: list[dict] = state.get("todos", [])

        # Find the original user request (last HumanMessage)
        user_request = self._extract_user_request(messages)
        if not user_request:
            return None

        # Summarise the latest agent action
        action_summary = self._summarise_latest_action(messages)

        # Build prompt
        prompt = self._build_prompt(user_request, current_todos, action_summary)

        try:
            response = self._llm.invoke([
                SystemMessage(content=_SUB_AGENT_SYSTEM),
                HumanMessage(content=prompt),
            ])
            new_todos = self._parse_response(response.content)
            if new_todos is not None and new_todos != current_todos:
                logger.debug("Todo sub-agent updated: %s", new_todos)
                return {"todos": new_todos}
        except Exception:
            logger.warning("Todo sub-agent call failed", exc_info=True)

        return None

    def _extract_user_request(self, messages: list) -> str | None:
        """Find the most recent user message."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                return content if isinstance(content, str) else str(content)
            # Also handle dict-style messages from the input
            if isinstance(msg, dict) and msg.get("role") == "user":
                return str(msg.get("content", ""))
        return None

    def _summarise_latest_action(self, messages: list) -> str:
        """Build a concise summary of what just happened."""
        parts: list[str] = []

        # Walk backwards to find the last AI message and any preceding tool results
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_names = [tc.get("name", "?") for tc in msg.tool_calls]
                    parts.append(f"Agent正在调用工具: {', '.join(tool_names)}")
                elif msg.content:
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    # Truncate long content
                    if len(content) > 200:
                        content = content[:200] + "..."
                    parts.append(f"Agent回复: {content}")
                break

        # Check for recent tool results (before the last AI message)
        from langchain_core.messages import ToolMessage

        tool_results: list[str] = []
        found_ai = False
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                if found_ai:
                    break  # Stop at the previous AI message
                found_ai = True
                continue
            if found_ai and isinstance(msg, ToolMessage):
                name = getattr(msg, "name", "unknown")
                status = getattr(msg, "status", "success")
                tool_results.append(f"{name}({status})")

        if tool_results:
            parts.append(f"已完成的工具: {', '.join(reversed(tool_results))}")

        return "\n".join(parts) if parts else "Agent刚开始处理"

    def _build_prompt(
        self,
        user_request: str,
        current_todos: list[dict],
        action_summary: str,
    ) -> str:
        """Build the minimal prompt for the sub-agent."""
        todos_text = (
            json.dumps(current_todos, ensure_ascii=False, indent=2)
            if current_todos
            else "无（需要创建初始计划）"
        )

        return (
            f"用户请求: {user_request}\n\n"
            f"当前任务列表:\n{todos_text}\n\n"
            f"最新动态:\n{action_summary}"
        )

    def _parse_response(self, content: str | list) -> list[dict] | None:
        """Parse the sub-agent's JSON response into a todo list."""
        if not content:
            return None

        text = content if isinstance(content, str) else str(content)

        # Try to extract JSON array from the response
        # Handle cases where LLM wraps in markdown code blocks
        json_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
        if json_match:
            text = json_match.group(1)
        else:
            # Try to find a raw JSON array
            arr_match = re.search(r"\[[\s\S]*\]", text)
            if arr_match:
                text = arr_match.group(0)

        try:
            data = json.loads(text)
            if not isinstance(data, list):
                return None
            # Validate and normalise
            todos: list[dict] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                content_val = item.get("content", "")
                status = item.get("status", "pending")
                if status not in ("pending", "in_progress", "completed"):
                    status = "pending"
                if content_val:
                    todos.append({"content": content_val, "status": status})
            return todos if todos else None
        except (json.JSONDecodeError, TypeError):
            logger.warning("Todo sub-agent returned invalid JSON: %s", text[:200])
            return None
