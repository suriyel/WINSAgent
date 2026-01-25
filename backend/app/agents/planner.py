"""
Planner SubGraph - 任务规划Agent
负责：意图解析、任务拆解、依赖推断
"""

import json
import re
from typing import Literal, Any
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from .state import AgentState, TodoStep, create_todo_step
from .llm import get_llm
from .context_manager import get_context_manager
from app.tools.base import ToolRegistry
from app.config import get_settings


class TaskStep(BaseModel):
    """单个任务步骤"""
    description: str = Field(description="步骤描述")
    tool_name: str | None = Field(default=None, description="使用的工具名称，如不需要工具则为null")
    depends_on: list[str] = Field(default_factory=list, description="依赖的前置步骤ID列表")
    requires_user_input: bool = Field(default=False, description="是否需要用户输入")


class TaskPlan(BaseModel):
    """任务规划结构"""
    intent: str = Field(description="用户意图概述")
    steps: list[TaskStep] = Field(description="任务步骤列表")


def get_available_tools_description() -> str:
    """获取可用工具的描述列表"""
    tools = ToolRegistry.get_all()
    if not tools:
        return "当前无可用工具"

    tool_descriptions = []
    for t in tools:
        tool_descriptions.append(f"- {t.name}: {t.description}")
    return "\n".join(tool_descriptions)


PLANNER_SYSTEM_PROMPT = """你是一个专业的任务规划专家。你的职责是：
1. 准确理解用户的自然语言输入，提取核心意图
2. 将复杂任务拆解为可执行的步骤列表
3. 识别步骤之间的依赖关系
4. 为每个步骤匹配合适的工具

## 可用工具列表
{tools}

## 输出格式要求
请严格按照以下JSON格式输出任务规划，不要包含任何额外文字：
```json
{{
  "intent": "用户意图的简短描述",
  "steps": [
    {{
      "id": "step_1",
      "description": "步骤描述",
      "tool_name": "工具名称或null",
      "depends_on": [],
      "requires_user_input": false
    }},
    {{
      "id": "step_2",
      "description": "步骤描述",
      "tool_name": "工具名称或null",
      "depends_on": ["step_1"],
      "requires_user_input": false
    }}
  ]
}}
```

## 规划原则
- 每个步骤应该原子化，只做一件事
- 步骤ID格式为 step_1, step_2, step_3...
- 正确设置步骤之间的依赖关系
- 如果某步骤需要用户提供信息，设置 requires_user_input 为 true
- 如果不需要使用工具，tool_name 设为 null
- 步骤数量控制在1-10个之间
"""


def parse_plan_response(content: str) -> dict[str, Any] | None:
    """解析 LLM 返回的规划结果"""
    # 尝试提取 JSON 代码块
    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # 尝试直接解析整个内容
        json_str = content

    try:
        # 清理可能的多余字符
        json_str = json_str.strip()
        if json_str.startswith('```'):
            json_str = json_str[3:]
        if json_str.endswith('```'):
            json_str = json_str[:-3]

        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def planner_node(state: AgentState) -> dict:
    """Planner 节点 - 解析意图并生成 TODO 列表"""
    settings = get_settings()
    llm = get_llm()

    # 获取可用工具描述
    tools_desc = get_available_tools_description()
    system_prompt = PLANNER_SYSTEM_PROMPT.format(tools=tools_desc)

    # 使用上下文管理器优化消息历史
    context_mgr = get_context_manager(settings.message_token_limit)
    optimized_messages = context_mgr.optimize_context(state)

    # 构建消息
    messages = [
        SystemMessage(content=system_prompt),
        *optimized_messages,
        HumanMessage(
            content="请分析上述用户需求，按照指定的JSON格式生成任务规划。"
        ),
    ]

    # 调用 LLM 获取规划
    response = llm.invoke(messages)
    content = response.content

    # 解析响应
    plan_data = parse_plan_response(content)

    todo_list: list[TodoStep] = []
    parsed_intent = ""

    if plan_data and "steps" in plan_data:
        parsed_intent = plan_data.get("intent", "")

        for step_data in plan_data["steps"]:
            step_id = step_data.get("id", f"step_{len(todo_list) + 1}")

            # 如果需要用户输入，工具名设为 user_input
            tool_name = step_data.get("tool_name")
            if step_data.get("requires_user_input"):
                tool_name = "user_input"

            todo_list.append(
                create_todo_step(
                    step_id=step_id,
                    description=step_data.get("description", "未知步骤"),
                    tool_name=tool_name,
                    depends_on=step_data.get("depends_on", []),
                )
            )
    else:
        # 解析失败，创建一个通用步骤
        parsed_intent = "处理用户请求"
        todo_list = [
            create_todo_step(
                step_id="step_1",
                description="理解并处理用户请求",
                tool_name=None,
            ),
        ]

    # 生成用户可见的规划说明
    plan_summary = f"**任务规划完成**\n\n目标：{parsed_intent}\n\n已生成 {len(todo_list)} 个执行步骤。"

    return {
        "messages": [AIMessage(content=plan_summary, metadata={"internal": True})],
        "parsed_intent": parsed_intent,
        "todo_list": todo_list,
        "current_step": 0,
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
