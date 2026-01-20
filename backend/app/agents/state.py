"""
Agent State 定义
基于 LangGraph 1.0 标准模式
"""

from typing import Annotated, TypedDict, Literal, Any
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class TodoStep(TypedDict):
    """单个任务步骤"""

    id: str
    description: str
    tool_name: str | None
    status: Literal["pending", "running", "completed", "failed"]
    result: str | None
    error: str | None
    depends_on: list[str]
    progress: int
    retry_count: int  # 重试次数


class PendingConfigField(TypedDict):
    """配置字段"""

    name: str
    label: str
    field_type: str
    required: bool
    default: Any
    options: list[dict] | None
    placeholder: str | None
    description: str | None


class PendingConfig(TypedDict):
    """待用户配置"""

    step_id: str
    title: str
    description: str | None
    fields: list[PendingConfigField]
    values: dict[str, Any]


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
    current_agent: Literal["supervisor", "planner", "executor", "validator"] | None


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
