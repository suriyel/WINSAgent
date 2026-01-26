"""
Human-in-the-Loop 工具

基于 LangGraph 原生 interrupt() 实现人机交互:
- request_human_approval: 请求人工授权
- request_human_input: 请求人工输入
"""

from typing import Literal, Any

from langchain_core.tools import tool
from langgraph.types import interrupt
from pydantic import BaseModel, Field


# ============== 数据模型 ==============


class ApprovalRequest(BaseModel):
    """授权请求"""

    type: Literal["authorization"] = "authorization"
    action: str = Field(description="需要授权的操作描述")
    tool_name: str = Field(description="工具名称")
    params: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    reason: str | None = Field(default=None, description="请求原因")


class ApprovalResponse(BaseModel):
    """授权响应"""

    action: Literal["approve", "reject", "edit"] = Field(description="用户操作")
    reason: str | None = Field(default=None, description="拒绝原因")
    params: dict[str, Any] | None = Field(default=None, description="修改后的参数")


class InputRequest(BaseModel):
    """输入请求"""

    type: Literal["input_required"] = "input_required"
    question: str = Field(description="问题")
    context: str | None = Field(default=None, description="上下文")
    input_type: Literal["text", "choice", "confirm"] = Field(
        default="text", description="输入类型"
    )
    choices: list[str] | None = Field(default=None, description="选项列表 (choice 类型)")


class InputResponse(BaseModel):
    """输入响应"""

    input: str = Field(description="用户输入")


# ============== 工具定义 ==============


class RequestApprovalInput(BaseModel):
    """request_human_approval 输入参数"""

    action: str = Field(description="需要用户授权的操作描述，要清晰说明将要做什么")
    tool_name: str = Field(description="将要调用的工具名称")
    params: dict[str, Any] = Field(
        default_factory=dict, description="工具调用参数"
    )
    reason: str | None = Field(
        default=None, description="请求授权的原因，帮助用户理解为什么需要授权"
    )


@tool(args_schema=RequestApprovalInput)
def request_human_approval(
    action: str,
    tool_name: str,
    params: dict[str, Any] = None,
    reason: str | None = None,
) -> str:
    """
    请求人工授权。当执行敏感操作或重要决策时，暂停执行等待用户确认。

    使用场景:
    - 执行可能有副作用的操作前 (如写文件、发送邮件)
    - 执行成本较高的操作前 (如 API 调用)
    - 需要用户确认参数正确性时

    用户可以:
    - approve: 批准执行，继续原计划
    - reject: 拒绝执行，提供原因
    - edit: 修改参数后执行

    Args:
        action: 操作描述
        tool_name: 工具名称
        params: 工具参数
        reason: 请求原因

    Returns:
        用户的响应结果
    """
    if params is None:
        params = {}

    # 创建中断请求
    request = ApprovalRequest(
        action=action,
        tool_name=tool_name,
        params=params,
        reason=reason,
    )

    # interrupt() 暂停图执行，返回给客户端
    # 客户端通过 Command(resume=...) 恢复执行
    human_response = interrupt(request.model_dump())

    # 解析用户响应
    if isinstance(human_response, dict):
        response = ApprovalResponse(**human_response)
    else:
        # 简单响应，视为批准
        return f"用户已批准执行 {tool_name}"

    if response.action == "approve":
        return f"用户已批准执行 {tool_name}，参数: {params}"

    elif response.action == "reject":
        reason_text = f"，原因: {response.reason}" if response.reason else ""
        return f"用户拒绝执行 {tool_name}{reason_text}"

    elif response.action == "edit":
        if response.params:
            return f"用户修改了参数，新参数: {response.params}"
        return f"用户选择编辑但未提供新参数"

    return f"未知的用户响应: {response.action}"


class RequestInputInput(BaseModel):
    """request_human_input 输入参数"""

    question: str = Field(description="需要用户回答的问题，要清晰具体")
    context: str | None = Field(
        default=None, description="上下文信息，帮助用户理解问题背景"
    )
    input_type: Literal["text", "choice", "confirm"] = Field(
        default="text",
        description="输入类型: text(自由文本), choice(选择), confirm(是否确认)",
    )
    choices: list[str] | None = Field(
        default=None, description="选项列表，仅在 input_type='choice' 时使用"
    )


@tool(args_schema=RequestInputInput)
def request_human_input(
    question: str,
    context: str | None = None,
    input_type: Literal["text", "choice", "confirm"] = "text",
    choices: list[str] | None = None,
) -> str:
    """
    请求人工输入。当需要用户提供额外信息时使用。

    使用场景:
    - 缺少必要参数，需要用户提供
    - 存在多个选项，需要用户选择
    - 需要用户确认某个假设或理解

    Args:
        question: 问题描述
        context: 上下文信息
        input_type: 输入类型
        choices: 选项列表 (choice 类型时必填)

    Returns:
        用户的输入内容
    """
    # 创建中断请求
    request = InputRequest(
        question=question,
        context=context,
        input_type=input_type,
        choices=choices,
    )

    # interrupt() 暂停图执行
    human_response = interrupt(request.model_dump())

    # 解析用户响应
    if isinstance(human_response, dict):
        response = InputResponse(**human_response)
        return response.input
    elif isinstance(human_response, str):
        return human_response
    else:
        return str(human_response)


# ============== 工具包装器 ==============


def create_approval_wrapper(tool_func, tool_name: str):
    """
    创建需要授权的工具包装器

    使用方式:
        wrapped_tool = create_approval_wrapper(original_tool, "tool_name")
    """
    from langchain_core.tools import StructuredTool

    original_schema = tool_func.args_schema

    def wrapped_func(**kwargs):
        # 先请求授权
        approval_result = request_human_approval.invoke({
            "action": f"执行 {tool_name}",
            "tool_name": tool_name,
            "params": kwargs,
        })

        # 检查是否批准
        if "拒绝" in approval_result:
            return approval_result

        # 批准后执行原工具
        return tool_func.invoke(kwargs)

    return StructuredTool.from_function(
        func=wrapped_func,
        name=f"{tool_name}_with_approval",
        description=f"[需要授权] {tool_func.description}",
        args_schema=original_schema,
    )


def get_hitl_tools() -> list:
    """获取所有 HITL 相关工具"""
    return [request_human_approval, request_human_input]
