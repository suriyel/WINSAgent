"""
SubAgent 模块

通过 agent.as_tool() 模式实现专业化子代理:
- planner: 任务规划专家
- validator: 结果验证专家
- research: 研究分析专家
"""

from .planner import create_planner_tool
from .validator import create_validator_tool
from .research import create_research_tool

__all__ = [
    "create_planner_tool",
    "create_validator_tool",
    "create_research_tool",
]


def get_subagent_tools(model=None):
    """
    获取所有 SubAgent 工具

    Args:
        model: LLM 模型实例，如果为 None 则使用默认模型

    Returns:
        SubAgent 工具列表
    """
    if model is None:
        from app.agents.llm import get_llm
        model = get_llm()

    return [
        create_planner_tool(model),
        create_validator_tool(model),
        create_research_tool(model),
    ]
