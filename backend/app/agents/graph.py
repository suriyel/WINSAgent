"""
主 Agent Graph 组装
"""

from typing import Callable
from functools import lru_cache
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver

from .state import AgentState
from .supervisor import supervisor_node, route_supervisor
from .planner import planner_node
from .executor import executor_node
from .validator import validator_node
from .replanner import replanner_node
from app.config import get_settings
from app.tools.base import get_default_tools


def build_agent_graph(
    tools: list[BaseTool] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> StateGraph:
    """构建完整的 Agent Graph

    Args:
        tools: 可用的工具列表
        checkpointer: 状态持久化器

    Returns:
        编译后的 StateGraph
    """
    settings = get_settings()
    builder = StateGraph(AgentState)

    # 添加节点
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("planner", planner_node)

    # Executor 节点需要传入 tools
    def executor_with_tools(state: AgentState) -> dict:
        return executor_node(state, tools)

    builder.add_node("executor", executor_with_tools)
    builder.add_node("validator", validator_node)

    # 添加 Replanner 节点（动态重规划）
    builder.add_node("replanner", replanner_node)

    # 入口边
    builder.add_edge(START, "supervisor")

    # Supervisor 条件路由（包含 replanner）
    builder.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "planner": "planner",
            "executor": "executor",
            "validator": "validator",
            "replanner": "replanner",
            "end": END,
        },
    )

    # SubGraph 返回 Supervisor
    builder.add_edge("planner", "supervisor")
    builder.add_edge("executor", "supervisor")
    builder.add_edge("replanner", "supervisor")  # Replanner 返回 Supervisor
    builder.add_edge("validator", END)

    # 编译参数
    compile_kwargs = {}

    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer

    # 注意：不设置 interrupt_before，因为我们使用 interrupt() 函数手动触发中断
    # interrupt() 函数会在执行过程中动态暂停执行

    return builder.compile(**compile_kwargs)


# 全局 Graph 实例缓存
_graph_instance = None
_checkpointer_instance = None


def get_checkpointer() -> BaseCheckpointSaver:
    """获取 Checkpointer 实例

    - 开发环境：使用内存存储 (InMemorySaver)
    - 生产环境：使用 Redis 存储 (RedisSaver)
    """
    global _checkpointer_instance

    if _checkpointer_instance is None:
        settings = get_settings()

        if settings.debug:
            # 开发环境使用内存存储
            _checkpointer_instance = InMemorySaver()
        else:
            # 生产环境使用 Redis
            try:
                from langgraph.checkpoint.redis import RedisSaver
                _checkpointer_instance = RedisSaver.from_conn_string(settings.redis_url)
            except ImportError:
                # 如果 Redis 不可用，回退到内存存储
                _checkpointer_instance = InMemorySaver()

    return _checkpointer_instance


def get_agent_graph(tools: list[BaseTool] | None = None) -> StateGraph:
    """获取 Agent Graph 单例

    Args:
        tools: 可用的工具列表，如果为 None 则使用默认工具

    Returns:
        编译后的 StateGraph
    """
    global _graph_instance

    if _graph_instance is None:
        # 如果没有提供工具，使用默认工具
        if tools is None:
            tools = get_default_tools()

        checkpointer = get_checkpointer()
        _graph_instance = build_agent_graph(tools, checkpointer)

    return _graph_instance


def reset_graph():
    """重置 Graph 实例（用于测试）"""
    global _graph_instance, _checkpointer_instance
    _graph_instance = None
    _checkpointer_instance = None
