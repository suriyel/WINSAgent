"""
API 数据模型定义
"""

from typing import Literal, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class TodoStatus(str, Enum):
    """TODO 步骤状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskStatus(str, Enum):
    """任务整体状态"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    WAITING_INPUT = "waiting_input"


class TodoStep(BaseModel):
    """单个任务步骤"""

    id: str = Field(..., description="步骤唯一标识")
    description: str = Field(..., description="步骤描述")
    tool_name: str | None = Field(None, description="关联的工具名称")
    status: TodoStatus = Field(TodoStatus.PENDING, description="步骤状态")
    result: str | None = Field(None, description="执行结果")
    error: str | None = Field(None, description="错误信息")
    depends_on: list[str] = Field(default_factory=list, description="依赖的步骤ID列表")
    started_at: datetime | None = Field(None, description="开始时间")
    completed_at: datetime | None = Field(None, description="完成时间")
    progress: int = Field(0, ge=0, le=100, description="进度百分比")


class ConfigFormField(BaseModel):
    """配置表单字段 - 支持嵌套和集合类型"""

    name: str = Field(..., description="字段名称")
    label: str = Field(..., description="字段标签")
    field_type: Literal["text", "number", "select", "switch", "chips", "textarea", "object", "array"] = Field(
        ..., description="字段类型"
    )
    required: bool = Field(False, description="是否必填")
    default: Any = Field(None, description="默认值")
    options: list[dict[str, Any]] | None = Field(None, description="选项列表(select/chips)")
    placeholder: str | None = Field(None, description="占位符")
    description: str | None = Field(None, description="字段说明")
    # 嵌套类型支持
    children: list['ConfigFormField'] | None = Field(None, description="object 类型的子字段")
    item_type: 'ConfigFormField | None' = Field(None, description="array 类型的元素定义")


class PendingConfig(BaseModel):
    """待用户填充的配置 - 支持两种中断场景"""

    step_id: str = Field(..., description="关联的步骤ID")
    title: str = Field(..., description="配置标题")
    description: str | None = Field(None, description="配置说明")
    fields: list[ConfigFormField] = Field(..., description="表单字段列表")
    values: dict[str, Any] = Field(default_factory=dict, description="用户填充的值")
    # 中断类型
    interrupt_type: Literal["param_required", "authorization"] = Field(
        "authorization", description="中断类型"
    )
    # 授权场景专用
    tool_name: str | None = Field(None, description="待授权的工具名")
    tool_args: dict[str, Any] | None = Field(None, description="工具的完整参数")


class ChatMessage(BaseModel):
    """聊天消息"""

    role: Literal["user", "assistant", "system"] = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(default_factory=datetime.now, description="消息时间")
    metadata: dict[str, Any] | None = Field(None, description="元数据")


class ChatRequest(BaseModel):
    """聊天请求"""

    message: str = Field(..., description="用户消息")
    thread_id: str | None = Field(None, description="会话线程ID")
    config_response: dict[str, Any] | None = Field(None, description="用户配置响应")


class ChatResponse(BaseModel):
    """聊天响应"""

    thread_id: str = Field(..., description="会话线程ID")
    message: ChatMessage = Field(..., description="助手消息")
    todo_list: list[TodoStep] = Field(default_factory=list, description="任务步骤列表")
    pending_config: PendingConfig | None = Field(None, description="待配置项")
    task_status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")


class TaskInfo(BaseModel):
    """任务信息"""

    task_id: str = Field(..., description="任务ID")
    thread_id: str = Field(..., description="会话线程ID")
    title: str = Field(..., description="任务标题")
    status: TaskStatus = Field(..., description="任务状态")
    progress: int = Field(0, ge=0, le=100, description="进度百分比")
    todo_list: list[TodoStep] = Field(default_factory=list, description="步骤列表")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class TaskListResponse(BaseModel):
    """任务列表响应"""

    tasks: list[TaskInfo] = Field(..., description="任务列表")
    total: int = Field(..., description="总数")


class ConversationInfo(BaseModel):
    """对话信息"""

    thread_id: str = Field(..., description="会话线程ID")
    title: str = Field(..., description="对话标题")
    last_message: str | None = Field(None, description="最后一条消息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class ConversationListResponse(BaseModel):
    """对话列表响应"""

    conversations: list[ConversationInfo] = Field(..., description="对话列表")
    total: int = Field(..., description="总数")


# 重建模型以支持自引用类型
ConfigFormField.model_rebuild()
