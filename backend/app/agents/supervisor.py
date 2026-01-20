"""
Supervisor Agent - 任务协调
负责：分析用户意图，协调 Planner/Executor/Validator
"""

from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.tools import tool
from langgraph.types import Command

from .state import AgentState, TodoStep
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


def get_step_summary(todo_list: list[TodoStep]) -> dict:
    """获取步骤状态摘要"""
    if not todo_list:
        return {"total": 0, "completed": 0, "failed": 0, "pending": 0, "running": 0}

    return {
        "total": len(todo_list),
        "completed": sum(1 for s in todo_list if s["status"] == "completed"),
        "failed": sum(1 for s in todo_list if s["status"] == "failed"),
        "pending": sum(1 for s in todo_list if s["status"] == "pending"),
        "running": sum(1 for s in todo_list if s["status"] == "running"),
    }


def get_next_pending_step(todo_list: list[TodoStep]) -> TodoStep | None:
    """获取下一个待执行的步骤"""
    for step in todo_list:
        if step["status"] == "pending":
            return step
    return None


def supervisor_node(state: AgentState) -> dict:
    """Supervisor 节点 - 协调决策"""
    # 分析当前状态
    todo_list = state.get("todo_list", [])
    current_step = state.get("current_step", 0)
    final_status = state.get("final_status")
    pending_config = state.get("pending_config")

    # 获取步骤摘要
    summary = get_step_summary(todo_list)

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

    # 检查执行状态
    all_completed = summary["completed"] == summary["total"]
    has_failed = summary["failed"] > 0
    has_pending = summary["pending"] > 0

    if all_completed:
        # 全部完成，需要校验
        return {
            "current_agent": "supervisor",
            "messages": [AIMessage(content="所有步骤执行完成，正在验证结果...")],
        }

    if has_failed and not has_pending:
        # 有失败且没有待执行步骤，进入校验
        return {
            "current_agent": "supervisor",
            "messages": [AIMessage(
                content=f"执行遇到问题：{summary['completed']} 个步骤完成，{summary['failed']} 个步骤失败。正在分析..."
            )],
        }

    # 有待执行步骤，继续执行
    next_step = get_next_pending_step(todo_list)
    if next_step:
        progress = f"{summary['completed']}/{summary['total']}"
        return {
            "current_agent": "supervisor",
            "messages": [AIMessage(
                content=f"执行进度: {progress}，正在处理：{next_step['description']}"
            )],
        }

    # 默认继续执行
    return {
        "current_agent": "supervisor",
        "messages": [AIMessage(content="继续执行任务...")],
    }


def route_supervisor(state: AgentState) -> str:
    """Supervisor 路由决策

    决策逻辑：
    1. 如果有待处理的用户配置或状态为等待输入 -> 结束
    2. 如果任务已完成（成功/失败）-> 结束
    3. 如果没有 todo_list -> 规划器
    4. 如果所有步骤完成或有失败且无待执行 -> 校验器
    5. 否则 -> 执行器
    """
    todo_list = state.get("todo_list", [])
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

    # 获取状态摘要
    summary = get_step_summary(todo_list)

    # 全部完成 -> 校验
    if summary["completed"] == summary["total"]:
        return "validator"

    # 有失败且没有待执行步骤 -> 校验
    if summary["failed"] > 0 and summary["pending"] == 0:
        return "validator"

    # 有待执行或运行中的步骤 -> 执行器
    return "executor"
