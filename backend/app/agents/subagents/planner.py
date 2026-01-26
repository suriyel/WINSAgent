"""
规划专家 SubAgent

职责:
- 分析用户意图
- 将复杂任务分解为可执行步骤
- 评估依赖关系和风险
"""

from typing import List, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent


PLANNER_SYSTEM_PROMPT = """你是一个专业的任务规划专家。

你的职责是分析用户的任务需求，并将其分解为清晰、可执行的步骤。

## 输出格式

请按以下格式输出你的分析:

### 1. 目标理解
简要描述你对任务目标的理解，确保准确把握用户意图。

### 2. 步骤分解
将任务分解为具体步骤，每个步骤应该:
- 明确具体，可独立执行
- 按逻辑顺序排列
- 标注可能需要的工具或资源

格式:
1. [步骤描述] - 工具: xxx
2. [步骤描述] - 工具: xxx
...

### 3. 依赖关系
说明步骤之间的依赖关系，哪些可以并行执行。

### 4. 风险评估
- 可能的失败点
- 备选方案
- 需要用户确认的决策点

## 注意事项

- 步骤要足够细致，确保可执行性
- 考虑边界情况和错误处理
- 如有不确定的地方，明确指出需要用户澄清
- 复杂任务建议分阶段执行，每阶段有明确的检查点
"""


class PlannerInput(TypedDict):
    """规划专家输入"""
    messages: List[dict]


def create_planner_tool(model: BaseChatModel) -> BaseTool:
    """
    创建规划专家工具

    Args:
        model: LLM 模型实例

    Returns:
        作为工具的规划专家 Agent
    """
    # 规划专家不需要工具，纯推理
    planner_agent = create_react_agent(
        model=model,
        tools=[],
        prompt=PLANNER_SYSTEM_PROMPT,
    )

    # 转换为工具
    planner_tool = planner_agent.as_tool(
        name="planner_expert",
        description="""规划专家。当收到复杂任务需要制定执行计划时调用。

使用场景:
- 用户提出的任务涉及多个步骤
- 需要分析任务可行性
- 需要评估依赖关系和风险

输入: 包含任务描述的消息列表
输出: 详细的执行计划，包括步骤、依赖和风险评估""",
        arg_types={"messages": List[dict]},
    )

    return planner_tool
