"""
Planner SubGraph - 任务规划Agent
负责：意图解析、任务拆解、依赖推断
"""

from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from .state import AgentState, TodoStep, create_todo_step
from .llm import get_llm


class TaskPlan(BaseModel):
    """任务规划结构"""

    intent: str = Field(description="用户意图概述")
    steps: list[dict] = Field(description="任务步骤列表")


PLANNER_SYSTEM_PROMPT = """你是一个专业的任务规划专家。你的职责是：
1. 准确理解用户的自然语言输入，提取核心意图
2. 将复杂任务拆解为可执行的步骤列表
3. 识别步骤之间的依赖关系

请按以下格式输出任务规划：
- 每个步骤需要包含：描述、可能需要的工具、依赖的前置步骤
- 步骤应该原子化，每个步骤只做一件事
- 确保步骤顺序符合逻辑依赖关系

注意：
- 不要自己执行任务，只做规划
- 如果需要用户提供额外信息，将其作为一个步骤
- 保持步骤简洁明了
"""


@tool
def generate_todo_list(
    intent: str,
    steps: list[dict],
) -> str:
    """生成任务步骤列表。

    Args:
        intent: 用户意图概述
        steps: 步骤列表，每个步骤包含 description, tool_name(可选), depends_on(可选)
    """
    return f"已生成 {len(steps)} 个步骤的任务规划"


def planner_node(state: AgentState) -> dict:
    """Planner 节点 - 解析意图并生成 TODO 列表"""
    llm = get_llm()

    # 构建消息
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        *state["messages"],
        HumanMessage(
            content="请分析上述用户需求，生成详细的任务步骤列表。每个步骤用JSON格式描述。"
        ),
    ]

    # 调用 LLM 获取规划
    response = llm.invoke(messages)

    # 解析响应，提取步骤（这里简化处理，实际可用 structured output）
    # 实际项目中应使用 response_format=ToolStrategy(TaskPlan)
    todo_list: list[TodoStep] = []

    # 示例：从响应中解析步骤
    # 这里需要根据实际 LLM 输出格式进行解析
    content = response.content

    # 简化示例：创建基础步骤
    if not state.get("todo_list"):
        todo_list = [
            create_todo_step(
                step_id="step_1",
                description="解析用户需求",
                tool_name=None,
            ),
            create_todo_step(
                step_id="step_2",
                description="执行任务",
                tool_name=None,
                depends_on=["step_1"],
            ),
            create_todo_step(
                step_id="step_3",
                description="验证结果",
                tool_name=None,
                depends_on=["step_2"],
            ),
        ]

    return {
        "messages": [AIMessage(content=content)],
        "parsed_intent": content[:200] if content else None,
        "todo_list": todo_list if todo_list else state.get("todo_list", []),
        "current_agent": "planner",
        "final_status": "running",
    }


def build_planner_graph() -> StateGraph:
    """构建 Planner SubGraph"""
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", END)

    return builder.compile()
