"""统一 SubAgent 扩展框架.

参考 deepagents SubAgentMiddleware 架构，扩展 reactive 自动触发能力。

使用方式:

    from app.agent.subagents import SubAgentMiddleware
    from app.agent.subagents.agents.todo_tracker import TODO_TRACKER_CONFIG

    subagent_mw = SubAgentMiddleware(
        delegated=[],                       # 委派式子 Agent 配置列表
        reactive=[TODO_TRACKER_CONFIG],     # 响应式子 Agent 配置列表
    )

    # 将 task() tool 注入主 Agent
    all_tools.extend(subagent_mw.tools)

    # 加入 middleware 管道
    middleware = [subagent_mw, ...]

添加新子 Agent:
    1. 在 agents/ 目录新建文件，定义 SubAgentConfig 或 ReactiveSubAgentConfig
    2. 如果是 reactive 且有新 state key，在 middleware.py 的 SubAgentState 中声明
    3. 在 core.py 中将配置加入 delegated 或 reactive 列表
"""

from app.agent.subagents.middleware import SubAgentMiddleware, SubAgentState
from app.agent.subagents.types import (
    CompiledSubAgent,
    ContextBuilder,
    ReactiveSubAgentConfig,
    ResultParser,
    SubAgentConfig,
    TriggerCondition,
)

__all__ = [
    "SubAgentMiddleware",
    "SubAgentState",
    "SubAgentConfig",
    "ReactiveSubAgentConfig",
    "CompiledSubAgent",
    "ContextBuilder",
    "ResultParser",
    "TriggerCondition",
]
