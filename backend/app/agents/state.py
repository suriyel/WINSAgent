"""
Agent State 定义
基于 LangGraph 1.0 标准模式
"""
from __future__ import annotations
from typing import Annotated, TypedDict, Literal, Any
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class TodoStep(TypedDict):
    """单个任务步骤"""

    id: str
    description: str
    tool_name: str | None
    status: Literal["pending", "running", "completed", "failed", "skipped"]  # 添加 skipped 状态
    result: str | None
    error: str | None
    depends_on: list[str]
    progress: int
    retry_count: int  # 重试次数


class ReplanContext(TypedDict):
    """重规划上下文 - 用于触发动态重规划"""

    trigger_reason: Literal[
        "max_retries_exceeded",  # 重试次数超限
        "goal_achieved_early",   # 目标提前达成
        "alternative_approach_needed",  # 需要替代方案
        "user_requested",        # 用户请求重规划
        "dependency_failed",     # 依赖步骤失败
    ]
    failed_step_id: str | None  # 失败步骤ID
    failed_step_error: str | None  # 失败错误信息
    completed_results: list[dict]  # 已完成步骤的结果摘要
    remaining_steps: list[str]  # 剩余步骤ID
    replan_count: int  # 当前重规划次数
    original_intent: str  # 原始用户意图


class PendingConfigField(TypedDict):
    """配置字段 - 支持嵌套和集合类型"""

    name: str
    label: str
    field_type: Literal[
        "text", "number", "textarea", "select", "switch", "chips",
        "object", "array"  # 复杂类型
    ]
    required: bool
    default: Any
    options: list[dict] | None
    placeholder: str | None
    description: str | None
    # 嵌套类型支持
    children: list[PendingConfigField] | None  # object 类型的子字段
    item_type: PendingConfigField | None  # array 类型的元素定义


class PendingConfig(TypedDict):
    """待用户配置 - 支持两种中断场景"""

    step_id: str
    title: str
    description: str | None
    fields: list[PendingConfigField]
    values: dict[str, Any]
    # 中断类型
    interrupt_type: Literal["param_required", "authorization"]
    # 授权场景专用
    tool_name: str | None  # 待授权的工具名
    tool_args: dict[str, Any] | None  # 工具的完整参数（授权场景展示用）


class AgentState(TypedDict):
    """Agent 工作台核心状态"""

    # 对话消息 - 使用 add_messages reducer 自动合并
    messages: Annotated[list[BaseMessage], add_messages]

    # 解析后的用户意图
    parsed_intent: str | None

    # 任务步骤列表
    todo_list: list[TodoStep]

    # 当前执行步骤索引
    current_step: int

    # 最终状态
    final_status: Literal["pending", "running", "success", "failed", "waiting_input"] | None

    # 需要用户输入的配置项
    pending_config: PendingConfig | None

    # 错误信息
    error_info: str | None

    # 当前活跃的 Agent
    current_agent: Literal["supervisor", "planner", "executor", "validator", "replanner"] | None

    # === 动态重规划相关字段 ===

    # 重规划上下文 - 触发重规划时填充
    replan_context: ReplanContext | None

    # 目标是否提前达成
    goal_achieved: bool

    # 目标评估结果说明
    goal_evaluation_result: str | None


def create_initial_state() -> AgentState:
    """创建初始状态"""
    return AgentState(
        messages=[],
        parsed_intent=None,
        todo_list=[],
        current_step=0,
        final_status="pending",
        pending_config=None,
        error_info=None,
        current_agent=None,
        replan_context=None,
        goal_achieved=False,
        goal_evaluation_result=None,
    )


def create_todo_step(
    step_id: str,
    description: str,
    tool_name: str | None = None,
    depends_on: list[str] | None = None,
) -> TodoStep:
    """创建 TODO 步骤"""
    return TodoStep(
        id=step_id,
        description=description,
        tool_name=tool_name,
        status="pending",
        result=None,
        error=None,
        depends_on=depends_on or [],
        progress=0,
        retry_count=0,
    )


def create_replan_context(
    trigger_reason: Literal[
        "max_retries_exceeded",
        "goal_achieved_early",
        "alternative_approach_needed",
        "user_requested",
        "dependency_failed",
    ],
    todo_list: list[TodoStep],
    original_intent: str,
    failed_step_id: str | None = None,
    failed_step_error: str | None = None,
    replan_count: int = 0,
) -> ReplanContext:
    """创建重规划上下文

    Args:
        trigger_reason: 触发重规划的原因
        todo_list: 当前任务列表
        original_intent: 原始用户意图
        failed_step_id: 失败步骤ID（如适用）
        failed_step_error: 失败错误信息（如适用）
        replan_count: 当前重规划次数

    Returns:
        ReplanContext 实例
    """
    # 收集已完成步骤的结果摘要
    completed_results = []
    for step in todo_list:
        if step["status"] == "completed":
            completed_results.append({
                "step_id": step["id"],
                "description": step["description"],
                "result": step.get("result", "")[:200] if step.get("result") else "",
            })

    # 收集剩余待执行步骤
    remaining_steps = [
        step["id"] for step in todo_list
        if step["status"] in ("pending", "running")
    ]

    return ReplanContext(
        trigger_reason=trigger_reason,
        failed_step_id=failed_step_id,
        failed_step_error=failed_step_error,
        completed_results=completed_results,
        remaining_steps=remaining_steps,
        replan_count=replan_count,
        original_intent=original_intent,
    )


def skip_remaining_steps(
    todo_list: list[TodoStep],
    after_step_id: str,
) -> list[TodoStep]:
    """将指定步骤之后的所有待执行步骤标记为 skipped

    Args:
        todo_list: 当前任务列表
        after_step_id: 从该步骤之后开始跳过

    Returns:
        更新后的任务列表
    """
    found_step = False
    updated_list = []

    for step in todo_list:
        if found_step and step["status"] == "pending":
            updated_list.append({
                **step,
                "status": "skipped",
                "result": "目标已提前达成，跳过此步骤",
            })
        else:
            updated_list.append(step)

        if step["id"] == after_step_id:
            found_step = True

    return updated_list
