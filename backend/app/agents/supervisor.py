"""
Supervisor Agent - 任务协调
负责：分析用户意图，协调 Planner/Executor/Validator/Replanner
"""

from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.tools import tool
from langgraph.types import Command

from .state import AgentState, TodoStep
from .llm import get_llm
from app.config import get_settings


SUPERVISOR_SYSTEM_PROMPT = """你是一个任务协调 Supervisor，负责：
1. 分析用户意图，决定下一步行动
2. 将任务交给 Planner 进行拆解
3. 协调 Executor 逐步执行任务
4. 在执行失败时协调 Replanner 重新规划
5. 将执行结果交给 Validator 校验

你不自己执行具体任务，只做协调调度。

根据当前状态，选择下一个要调用的 Agent：
- planner: 当需要解析用户意图、生成任务步骤时
- executor: 当有待执行的步骤时
- replanner: 当步骤失败且需要重新规划时
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
        return {"total": 0, "completed": 0, "failed": 0, "pending": 0, "running": 0, "skipped": 0}

    return {
        "total": len(todo_list),
        "completed": sum(1 for s in todo_list if s["status"] == "completed"),
        "failed": sum(1 for s in todo_list if s["status"] == "failed"),
        "pending": sum(1 for s in todo_list if s["status"] == "pending"),
        "running": sum(1 for s in todo_list if s["status"] == "running"),
        "skipped": sum(1 for s in todo_list if s["status"] == "skipped"),
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
    replan_context = state.get("replan_context")
    goal_achieved = state.get("goal_achieved", False)

    # 获取步骤摘要
    summary = get_step_summary(todo_list)

    # 决策逻辑

    # 1. 检查是否需要重规划
    if replan_context:
        return {
            "current_agent": "supervisor",
            "messages": [AIMessage(content="执行遇到问题，正在重新规划执行方案...")],
        }

    # 2. 检查目标是否提前达成
    if goal_achieved:
        goal_result = state.get("goal_evaluation_result", "")
        return {
            "current_agent": "supervisor",
            "messages": [AIMessage(
                content=f"目标已提前达成，正在验证结果... {goal_result}"
            )],
        }

    # 3. 等待用户输入
    if pending_config:
        return {
            "current_agent": "supervisor",
            "final_status": "waiting_input",
        }

    # 4. 需要规划
    if not todo_list:
        return {
            "current_agent": "supervisor",
            "messages": [AIMessage(content="正在分析您的需求，生成任务计划...")],
        }

    # 检查执行状态 - 注意 skipped 也算完成
    finished_count = summary["completed"] + summary["skipped"]
    all_finished = finished_count == summary["total"]
    has_failed = summary["failed"] > 0
    has_pending = summary["pending"] > 0

    if all_finished:
        # 全部完成（包括跳过的），需要校验
        return {
            "current_agent": "supervisor",
            "messages": [AIMessage(content="所有步骤执行完成，正在验证结果...")],
        }

    if has_failed and not has_pending:
        # 有失败且没有待执行步骤，进入校验或重规划
        settings = get_settings()
        if settings.replan_enabled and not replan_context:
            # 如果启用重规划但还没有 replan_context，说明需要检查是否触发重规划
            return {
                "current_agent": "supervisor",
                "messages": [AIMessage(
                    content=f"执行遇到问题：{summary['completed']} 个步骤完成，{summary['failed']} 个步骤失败。正在分析..."
                )],
            }
        else:
            return {
                "current_agent": "supervisor",
                "messages": [AIMessage(
                    content=f"执行遇到问题：{summary['completed']} 个步骤完成，{summary['failed']} 个步骤失败。正在分析..."
                )],
            }

    # 有待执行步骤，继续执行
    next_step = get_next_pending_step(todo_list)
    if next_step:
        progress = f"{finished_count}/{summary['total']}"
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
    3. 如果有重规划上下文 -> 重规划器
    4. 如果目标已提前达成 -> 校验器
    5. 如果没有 todo_list -> 规划器
    6. 如果所有步骤完成（包括跳过）或有失败且无待执行 -> 校验器
    7. 否则 -> 执行器
    """
    todo_list = state.get("todo_list", [])
    final_status = state.get("final_status")
    pending_config = state.get("pending_config")
    replan_context = state.get("replan_context")
    goal_achieved = state.get("goal_achieved", False)

    # 等待用户输入
    if pending_config or final_status == "waiting_input":
        return "end"

    # 任务已完成
    if final_status in ["success", "failed"]:
        return "end"

    # 有重规划上下文 -> 重规划器
    if replan_context:
        return "replanner"

    # 目标已提前达成 -> 校验器
    if goal_achieved:
        return "validator"

    # 需要规划
    if not todo_list:
        return "planner"

    # 获取状态摘要
    summary = get_step_summary(todo_list)

    # 计算完成数量（包括 skipped）
    finished_count = summary["completed"] + summary["skipped"]

    # 全部完成（包括跳过的） -> 校验
    if finished_count == summary["total"]:
        return "validator"

    # 有失败且没有待执行步骤 -> 校验（重规划会在 executor 中触发）
    if summary["failed"] > 0 and summary["pending"] == 0:
        return "validator"

    # 有待执行或运行中的步骤 -> 执行器
    return "executor"
