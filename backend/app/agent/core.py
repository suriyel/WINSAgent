"""Agent core: builds the main Agent with middleware and tools."""

from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware.human_in_the_loop import HumanInTheLoopMiddleware
from langchain.agents.middleware.todo import TodoListMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.tools.demo_tools import register_demo_tools
from app.agent.tools.knowledge import register_knowledge_tools
from app.agent.subagents.data_analysis import register_subagent_tools
from app.agent.tools.registry import tool_registry
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是 WINS Agent 工作台的智能助手。你的核心职责是：

1. **理解用户意图**：准确识别用户需求，选取合适的工具完成任务。
2. **领域知识检索**：当遇到专业术语或需要系统设计信息时，主动调用 search_terminology 或 search_design_doc 工具获取上下文。
3. **工具编排**：根据工具的依赖关系，按正确顺序调用工具。例如创建订单前需先验证客户。
4. **参数填充**：结合领域知识和上下文，准确填写工具参数。
5. **任务规划**：使用 write_todos 工具记录任务步骤计划，便于用户跟踪进度。

注意事项：
- 工具调用失败时，整个任务终止，不要重试
- 需要HITL确认的操作会暂停等待用户批准
- 始终用中文回复用户
"""

# In-memory checkpointer for dev/validation stage
_checkpointer = InMemorySaver()

# Track whether tools have been registered
_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    register_demo_tools()
    register_knowledge_tools()
    register_subagent_tools()
    _initialized = True


def build_agent():
    """Build and return the main Agent (CompiledStateGraph)."""
    _ensure_initialized()

    all_tools = tool_registry.get_all_tools()
    hitl_config = tool_registry.get_hitl_config()

    middleware = [
        TodoListMiddleware(),
    ]
    # Only add HITL middleware when there are tools requiring it
    if hitl_config:
        middleware.append(
            HumanInTheLoopMiddleware(
                interrupt_on=hitl_config,
                description_prefix="该操作需要您确认",
            )
        )

    # 1. 配置通义千问的 OpenAI 兼容实例
    llm = ChatOpenAI(
        model=settings.llm_model,  # 例如 "qwen-max"
        openai_api_key=settings.llm_api_key,
        openai_api_base=settings.llm_base_url,
        streaming=True
    )

    agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=middleware,
        checkpointer=_checkpointer,
    )
    return agent


# Lazily-created singleton
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def get_checkpointer() -> InMemorySaver:
    return _checkpointer
