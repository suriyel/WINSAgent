"""
Supervisor Agent - 任务协调
负责：分析用户意图，协调 Planner/Executor/Validator
"""

from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.tools import tool
from langgraph.types import Command

from .state import AgentState
from .llm import get_llm


SUPERVISOR_SYSTEM_PROMPT = """你是一个任务协调 Supervisor，负责：
1. 分析用户意图，决定下一步行动
2. 将任务交给 Planner 进行拆解
3. 协调 Executor 逐步执行任务
4. 将执行结果交给 Validator 校验

你不自己执行具体任务，只做协调调度。

根据当前状态，选择下一个要调用的 Agent：
- planner: 当需要解析用户意图、生成任务步骤时
- executor: 当有待执行的步骤时
- validator: 当所有步骤执行完成，需要校验结果时
- end: 当任务完成或需要等待用户输入时

请输出你的决策和理由。
"""


@tool
def handoff_to_planner(task_description: str) -> str:
    """将任务交给规划Agent进行任务拆解。

    Args:
        task_description: 任务描述
    """
    return "handoff_to_planner"


@tool
def handoff_to_executor(step_id: str) -> str:
    """将具体步骤交给执行Agent执行。

    Args:
        step_id: 步骤ID
    """
    return "handoff_to_executor"


@tool
def handoff_to_validator(summary: str) -> str:
    """将执行结果交给校验Agent进行验证。

    Args:
        summary: 执行摘要
    """
    return "handoff_to_validator"


def supervisor_node(state: AgentState) -> dict:
    """Supervisor 节点 - 协调决策"""
    llm = get_llm()

    # 分析当前状态
    todo_list = state.get("todo_list", [])
    current_step = state.get("current_step", 0)
    final_status = state.get("final_status")
    pending_config = state.get("pending_config")

    # 决策逻辑
    if pending_config:
        # 等待用户输入
        return {
            "current_agent": "supervisor",
            "final_status": "waiting_input",
        }

    if not todo_list:
        # 需要规划
        return {
            "current_agent": "supervisor",
            "messages": [AIMessage(content="正在分析您的需求，生成任务计划...")],
        }

    # 检查是否所有步骤完成
    all_completed = all(s["status"] == "completed" for s in todo_list)
    any_failed = any(s["status"] == "failed" for s in todo_list)

    if all_completed or any_failed:
        # 需要校验
        return {
            "current_agent": "supervisor",
            "messages": [AIMessage(content="任务执行完成，正在验证结果...")],
        }

    # 继续执行
    return {
        "current_agent": "supervisor",
        "messages": [AIMessage(content="继续执行任务...")],
    }


def route_supervisor(state: AgentState) -> str:
    """Supervisor 路由决策"""
    todo_list = state.get("todo_list", [])
    current_step = state.get("current_step", 0)
    final_status = state.get("final_status")
    pending_config = state.get("pending_config")

    # 等待用户输入
    if pending_config or final_status == "waiting_input":
        return "end"

    # 任务已完成
    if final_status in ["success", "failed"]:
        return "end"

    # 需要规划
    if not todo_list:
        return "planner"

    # 检查执行状态
    all_completed = all(s["status"] == "completed" for s in todo_list)
    any_failed = any(s["status"] == "failed" for s in todo_list)

    if all_completed or any_failed:
        return "validator"

    # 继续执行
    return "executor"
