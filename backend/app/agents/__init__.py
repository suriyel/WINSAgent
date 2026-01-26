"""
WINS Agent v2 - 基于 LangGraph create_react_agent 的智能任务编排系统

核心组件:
- main_agent: 主 Agent 入口
- middleware: 上下文管理等中间件
- tools: 业务工具、系统工具 (todos, hitl)
- subagents: 专家 SubAgent (planner, validator, research)

v2 架构基于 LangGraph 原生能力:
- create_react_agent 替代手写的 supervisor/planner/executor/validator
- interrupt() 实现 HITL
- pre_model_hook 实现上下文管理
- agent.as_tool() 实现 SubAgent
"""

from .main_agent import (
    create_main_agent,
    get_agent,
    reset_agent,
    invoke_agent,
    stream_agent,
    get_agent_state,
    get_checkpointer,
    get_store,
)
from .llm import get_llm, get_summarization_model, get_llm_for_subagent

__all__ = [
    # Main Agent
    "create_main_agent",
    "get_agent",
    "reset_agent",
    "invoke_agent",
    "stream_agent",
    "get_agent_state",
    "get_checkpointer",
    "get_store",
    # LLM
    "get_llm",
    "get_summarization_model",
    "get_llm_for_subagent",
]


# ============== 向后兼容 (deprecated) ==============
# 以下导出保留用于兼容旧代码，新代码请使用上述 API

def get_agent_graph(*args, **kwargs):
    """
    [Deprecated] 使用 get_agent() 替代

    返回编译后的 Agent Graph
    """
    import warnings
    warnings.warn(
        "get_agent_graph() is deprecated, use get_agent() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_agent()


def build_agent_graph(*args, **kwargs):
    """
    [Deprecated] 使用 create_main_agent() 替代
    """
    import warnings
    warnings.warn(
        "build_agent_graph() is deprecated, use create_main_agent() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_main_agent(*args, **kwargs)
