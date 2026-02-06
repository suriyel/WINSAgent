"""统一的 Agent State Schema.

定义 Agent 的完整状态结构，整合所有 Middleware 的状态字段。
"""

from __future__ import annotations

from typing import Any

from langchain.agents import AgentState

from app.agent.middleware.suggestions import SpeechTemplateData


class WINSAgentState(AgentState):
    """WINS Agent 统一状态 Schema.

    整合所有 Middleware 的状态字段：
    - suggestions: 话术模板数据 (SuggestionsMiddleware)
    - todos: TODO 步骤列表 (SubAgentMiddleware)
    """

    # SuggestionsMiddleware - 话术模板
    suggestions: SpeechTemplateData | None

    # SubAgentMiddleware - TODO 步骤
    todos: list[dict[str, Any]]
