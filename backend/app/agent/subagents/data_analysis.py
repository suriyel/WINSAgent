"""Data analysis SubAgent — wrapped as a Tool for the main Agent."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.tools import tool

from app.agent.tools.registry import tool_registry


# ---------------------------------------------------------------------------
# Inner tools available only to the SubAgent
# ---------------------------------------------------------------------------

@tool
def query_database(sql_description: str) -> str:
    """根据自然语言描述执行数据查询（模拟）。

    参数说明：
    - sql_description: 描述所需数据的自然语言
    """
    return (
        f"查询结果 (描述: {sql_description}):\n"
        "| 月份 | 销售额 | 订单数 |\n"
        "|------|--------|--------|\n"
        "| 2026-01 | ¥1,250,000 | 328 |\n"
        "| 2025-12 | ¥980,000 | 276 |\n"
        "| 2025-11 | ¥1,100,000 | 301 |"
    )


@tool
def generate_summary(data: str) -> str:
    """对数据进行统计分析并生成摘要。

    参数说明：
    - data: 需要分析的原始数据文本
    """
    return (
        "数据分析摘要:\n"
        "- 近3个月平均销售额: ¥1,110,000\n"
        "- 环比增长率: 27.6%\n"
        "- 平均订单金额: ¥3,672"
    )


# ---------------------------------------------------------------------------
# SubAgent creation & Tool wrapper
# ---------------------------------------------------------------------------

_sub_agent = None


def _get_sub_agent():
    global _sub_agent
    if _sub_agent is None:
        from app.config import settings

        _sub_agent = create_agent(
            model=settings.llm_model,
            tools=[query_database, generate_summary],
            system_prompt=(
                "你是数据分析专家。你可以使用 query_database 查询数据，"
                "使用 generate_summary 生成分析摘要。请根据用户需求完成数据分析任务。"
            ),
        )
    return _sub_agent


@tool(
    "data_analysis",
    description=(
        "执行数据分析任务，包括数据查询和统计分析。"
        "适用于需要多步数据处理的复杂分析请求，如销售统计、趋势分析等。"
    ),
)
def call_data_analysis(query: str) -> str:
    """将复杂数据分析任务委派给数据分析专家SubAgent。"""
    agent = _get_sub_agent()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": query}]}
    )
    return result["messages"][-1].content


def register_subagent_tools() -> None:
    tool_registry.register(call_data_analysis, category="long_running")
