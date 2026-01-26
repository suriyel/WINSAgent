"""
任务计划管理工具

参考 deepagents 的 write_todos 模式，实现任务分解和进度跟踪。
使用 LangGraph Store 进行持久化。
"""

from datetime import datetime
from typing import Literal
import uuid

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_store
from pydantic import BaseModel, Field


# ============== 数据模型 ==============


class TodoStep(BaseModel):
    """任务步骤"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = Field(description="步骤描述")
    status: Literal["pending", "running", "completed", "failed", "skipped"] = Field(
        default="pending", description="步骤状态"
    )
    tool_name: str | None = Field(default=None, description="关联的工具名称")
    result: str | None = Field(default=None, description="执行结果")
    error: str | None = Field(default=None, description="错误信息")
    started_at: str | None = Field(default=None, description="开始时间")
    completed_at: str | None = Field(default=None, description="完成时间")


class TodoList(BaseModel):
    """任务列表"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str = Field(description="最终目标")
    steps: list[TodoStep] = Field(default_factory=list, description="步骤列表")
    current_step_index: int = Field(default=0, description="当前步骤索引")
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="创建时间",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="更新时间",
    )

    @property
    def progress(self) -> tuple[int, int]:
        """返回 (已完成数, 总数)"""
        completed = sum(
            1 for s in self.steps if s.status in ("completed", "skipped")
        )
        return completed, len(self.steps)

    @property
    def is_complete(self) -> bool:
        """是否所有步骤都已完成"""
        return all(s.status in ("completed", "skipped", "failed") for s in self.steps)

    @property
    def current_step(self) -> TodoStep | None:
        """获取当前步骤"""
        pending = [s for s in self.steps if s.status == "pending"]
        return pending[0] if pending else None


# ============== 工具函数 ==============


def _get_thread_id(config: RunnableConfig) -> str:
    """从配置中获取 thread_id"""
    return config.get("configurable", {}).get("thread_id", "default")


def _get_todo_list(config: RunnableConfig) -> TodoList | None:
    """从 Store 获取任务列表"""
    store = get_store()
    if store is None:
        return None

    thread_id = _get_thread_id(config)
    result = store.get(("todos",), thread_id)

    if result and result.value:
        return TodoList(**result.value)
    return None


def _save_todo_list(config: RunnableConfig, todo_list: TodoList) -> None:
    """保存任务列表到 Store"""
    store = get_store()
    if store is None:
        return

    thread_id = _get_thread_id(config)
    todo_list.updated_at = datetime.now().isoformat()
    store.put(("todos",), thread_id, todo_list.model_dump())


# ============== 工具定义 ==============


class WriteTodosInput(BaseModel):
    """write_todos 输入参数"""

    goal: str = Field(description="任务的最终目标，清晰描述要达成的结果")
    steps: list[str] = Field(
        description="步骤列表，每个步骤是一个简短的描述，按执行顺序排列"
    )


@tool(args_schema=WriteTodosInput)
def write_todos(goal: str, steps: list[str], config: RunnableConfig) -> str:
    """
    创建或更新任务计划。将复杂任务分解为可执行的步骤。

    使用场景:
    - 收到复杂任务时，先调用此工具进行规划
    - 需要修改现有计划时，重新调用此工具

    Args:
        goal: 最终目标描述，要清晰具体
        steps: 步骤列表，每个步骤应该是可独立执行的动作

    Returns:
        创建的任务计划摘要，包含目标和所有步骤
    """
    todo_list = TodoList(
        goal=goal,
        steps=[TodoStep(description=s) for s in steps],
    )

    _save_todo_list(config, todo_list)

    # 格式化输出
    steps_text = "\n".join(
        f"  {i + 1}. [ ] {s.description}" for i, s in enumerate(todo_list.steps)
    )

    return f"""任务计划已创建:

目标: {goal}

步骤:
{steps_text}

共 {len(todo_list.steps)} 个步骤。请按顺序执行，每完成一步调用 update_todo_step 更新状态。"""


@tool
def read_todos(config: RunnableConfig) -> str:
    """
    读取当前任务计划和执行进度。

    使用场景:
    - 需要查看当前任务状态时
    - 决定下一步行动前
    - 向用户汇报进度时

    Returns:
        当前任务计划的详细信息，包括每个步骤的状态和结果
    """
    todo_list = _get_todo_list(config)

    if todo_list is None:
        return "当前没有任务计划。如需创建，请使用 write_todos 工具。"

    completed, total = todo_list.progress

    # 状态图标映射
    status_icons = {
        "pending": "[ ]",
        "running": "[▶]",
        "completed": "[✓]",
        "failed": "[✗]",
        "skipped": "[—]",
    }

    steps_lines = []
    for i, step in enumerate(todo_list.steps):
        icon = status_icons.get(step.status, "[ ]")
        line = f"  {i + 1}. {icon} {step.description}"

        if step.result:
            # 截断过长的结果
            result_preview = (
                step.result[:100] + "..." if len(step.result) > 100 else step.result
            )
            line += f"\n      → {result_preview}"

        if step.error:
            line += f"\n      ✗ 错误: {step.error}"

        steps_lines.append(line)

    steps_text = "\n".join(steps_lines)

    # 当前步骤提示
    current = todo_list.current_step
    current_hint = (
        f"\n当前步骤: 第 {todo_list.steps.index(current) + 1} 步 - {current.description}"
        if current
        else "\n所有步骤已完成或失败"
    )

    return f"""任务进度: {completed}/{total}

目标: {todo_list.goal}

步骤:
{steps_text}
{current_hint}"""


class UpdateTodoStepInput(BaseModel):
    """update_todo_step 输入参数"""

    step_index: int = Field(
        description="步骤索引 (从 0 开始)，指定要更新的步骤"
    )
    status: Literal["pending", "running", "completed", "failed", "skipped"] = Field(
        description="新状态: pending(待执行), running(执行中), completed(已完成), failed(失败), skipped(跳过)"
    )
    result: str | None = Field(
        default=None, description="执行结果描述 (completed 时提供)"
    )
    error: str | None = Field(
        default=None, description="错误信息 (failed 时提供)"
    )


@tool(args_schema=UpdateTodoStepInput)
def update_todo_step(
    step_index: int,
    status: Literal["pending", "running", "completed", "failed", "skipped"],
    result: str | None = None,
    error: str | None = None,
    config: RunnableConfig = None,
) -> str:
    """
    更新任务步骤的执行状态。

    使用场景:
    - 开始执行某步骤时，设置为 running
    - 步骤执行完成时，设置为 completed 并提供结果
    - 步骤执行失败时，设置为 failed 并提供错误信息
    - 决定跳过某步骤时，设置为 skipped

    Args:
        step_index: 步骤索引 (从 0 开始)
        status: 新状态
        result: 执行结果 (可选)
        error: 错误信息 (可选)

    Returns:
        更新结果和当前任务状态摘要
    """
    todo_list = _get_todo_list(config)

    if todo_list is None:
        return "没有找到任务计划。请先使用 write_todos 创建计划。"

    if step_index < 0 or step_index >= len(todo_list.steps):
        return f"无效的步骤索引: {step_index}。有效范围: 0-{len(todo_list.steps) - 1}"

    step = todo_list.steps[step_index]
    old_status = step.status

    # 更新状态
    step.status = status

    if status == "running":
        step.started_at = datetime.now().isoformat()
    elif status in ("completed", "failed", "skipped"):
        step.completed_at = datetime.now().isoformat()

    if result:
        step.result = result
    if error:
        step.error = error

    _save_todo_list(config, todo_list)

    # 计算进度
    completed, total = todo_list.progress

    return f"""步骤 {step_index + 1} 已更新: {old_status} → {status}

步骤: {step.description}
{f'结果: {result}' if result else ''}
{f'错误: {error}' if error else ''}

总进度: {completed}/{total}"""


def get_todo_tools() -> list:
    """获取所有 Todo 相关工具"""
    return [write_todos, read_todos, update_todo_step]
