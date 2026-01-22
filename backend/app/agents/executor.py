"""
Executor SubGraph - 任务执行Agent
负责：Tool选择、参数填充、执行调度、重试处理
"""

import json
from typing import Any
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage, HumanMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from .state import AgentState, TodoStep, PendingConfigField
from .llm import get_llm, get_llm_with_tools
from .context_manager import get_context_manager
from app.tools.base import ToolRegistry
from app.config import get_settings


EXECUTOR_SYSTEM_PROMPT = """你是一个专业的任务执行专家。你的职责是：
1. 根据任务步骤选择合适的工具并调用
2. 准确填充工具所需参数
3. 处理工具调用结果

## 当前步骤信息
步骤ID: {step_id}
步骤描述: {step_description}
指定工具: {tool_name}

## 可用工具
{tools_info}

## 执行要求
- 如果指定了工具，请直接调用该工具
- 如果未指定工具但需要完成任务，请选择最合适的工具
- 如果不需要调用工具，直接给出执行结果
- 参数必须完整准确，从上下文中推断缺失的参数
"""


class ExecutorContext:
    """执行器上下文"""

    def __init__(self, tools: list[BaseTool] | None = None):
        self.tools = tools or ToolRegistry.get_all()
        self.tool_map = {tool.name: tool for tool in self.tools}

    def get_tool(self, name: str) -> BaseTool | None:
        return self.tool_map.get(name)

    def get_tools_info(self) -> str:
        """获取工具信息描述"""
        if not self.tools:
            return "无可用工具"

        info = []
        for tool in self.tools:
            schema = tool.args_schema
            if schema:
                fields = []
                for field_name, field_info in schema.model_fields.items():
                    required = field_info.is_required()
                    desc = field_info.description or ""
                    fields.append(f"    - {field_name}: {desc} {'(必填)' if required else '(可选)'}")
                params = "\n".join(fields)
                info.append(f"- {tool.name}: {tool.description}\n  参数:\n{params}")
            else:
                info.append(f"- {tool.name}: {tool.description}")
        return "\n".join(info)


def update_step_status(
    todo_list: list[TodoStep],
    step_id: str,
    status: str,
    result: str | None = None,
    error: str | None = None,
    progress: int = 0,
) -> list[TodoStep]:
    """更新步骤状态"""
    updated = []
    for step in todo_list:
        if step["id"] == step_id:
            updated.append(
                {
                    **step,
                    "status": status,
                    "result": result,
                    "error": error,
                    "progress": progress,
                }
            )
        else:
            updated.append(step)
    return updated


def get_current_step(state: AgentState) -> TodoStep | None:
    """获取当前待执行的步骤"""
    todo_list = state.get("todo_list", [])
    current_idx = state.get("current_step", 0)

    if current_idx < len(todo_list):
        return todo_list[current_idx]
    return None


def check_dependencies_met(step: TodoStep, todo_list: list[TodoStep]) -> bool:
    """检查步骤依赖是否满足"""
    depends_on = step.get("depends_on", [])
    if not depends_on:
        return True

    step_status = {s["id"]: s["status"] for s in todo_list}
    return all(step_status.get(dep_id) == "completed" for dep_id in depends_on)


def generate_config_fields_from_tool(tool: BaseTool) -> list[PendingConfigField]:
    """从工具 Schema 生成配置表单字段"""
    fields = []
    if not tool.args_schema:
        return fields

    for field_name, field_info in tool.args_schema.model_fields.items():
        field_type = "text"
        annotation = field_info.annotation

        # 根据类型推断字段类型
        if annotation == bool:
            field_type = "switch"
        elif annotation == int or annotation == float:
            field_type = "number"
        elif hasattr(annotation, "__origin__") and annotation.__origin__ is list:
            field_type = "chips"

        fields.append(PendingConfigField(
            name=field_name,
            label=field_info.description or field_name,
            field_type=field_type,
            required=field_info.is_required(),
            default=field_info.default if field_info.default is not None else None,
            options=None,
            placeholder=f"请输入{field_info.description or field_name}",
            description=field_info.description,
        ))

    return fields


def executor_node(state: AgentState, tools: list[BaseTool] | None = None) -> dict:
    """Executor 节点 - 执行当前步骤"""
    settings = get_settings()
    current_step = get_current_step(state)

    if not current_step:
        # 所有步骤已完成
        return {
            "current_agent": "executor",
            "final_status": "success",
        }

    todo_list = state.get("todo_list", [])
    step_id = current_step["id"]

    # 检查依赖
    if not check_dependencies_met(current_step, todo_list):
        return {
            "error_info": f"步骤 {step_id} 的依赖尚未完成",
            "current_agent": "executor",
        }

    # 更新步骤状态为运行中
    updated_list = update_step_status(
        todo_list, step_id, "running", progress=10
    )

    # 获取执行器上下文
    ctx = ExecutorContext(tools)
    tool_name = current_step.get("tool_name")

    # 处理用户输入请求
    if tool_name == "user_input":
        # 检查是否已经从 HITL 恢复（用户已提交输入）
        # 通过检查消息历史中最后一条消息是否包含 "用户输入"
        messages = state.get("messages", [])
        user_submitted = False
        user_input_content = None

        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, 'content') and "用户输入:" in str(last_msg.content):
                user_submitted = True
                # 提取用户输入内容
                user_input_content = str(last_msg.content).replace("用户输入: ", "")
                print(f"[EXECUTOR] Detected user input from resume: {user_input_content}")

        if user_submitted:
            # 用户已经提交输入，将步骤标记为完成
            print(f"[EXECUTOR] Completing user_input step with: {user_input_content}")
            updated_list = update_step_status(
                updated_list, step_id, "completed",
                result=user_input_content,
                progress=100,
            )
            return {
                "todo_list": updated_list,
                "current_step": state.get("current_step", 0) + 1,
                "pending_config": None,
                "final_status": "running",
                "current_agent": "executor",
            }
        else:
            # 还没有用户输入，需要请求
            pending_config_data = {
                "step_id": step_id,
                "title": "需要您的输入",
                "description": current_step["description"],
                "fields": [PendingConfigField(
                    name="user_response",
                    label="您的回答",
                    field_type="textarea",
                    required=True,
                    default=None,
                    options=None,
                    placeholder="请输入您的回答...",
                    description=current_step["description"],
                )],
                "values": {},
            }

            print(f"[EXECUTOR] Setting pending_config for step {step_id}")
            print(f"[EXECUTOR] pending_config_data: {pending_config_data}")

            # 直接返回状态更新，不使用 interrupt()
            # 改用 final_status = "waiting_input" 来标记需要用户输入
            return {
                "todo_list": updated_list,
                "pending_config": pending_config_data,
                "final_status": "waiting_input",
                "current_agent": "executor",
            }

    # 如果指定了工具，直接调用
    if tool_name:
        tool = ctx.get_tool(tool_name)
        if tool:
            return execute_tool_with_llm(state, current_step, tool, ctx, updated_list)
        else:
            # 工具不存在，标记失败
            updated_list = update_step_status(
                updated_list, step_id, "failed",
                error=f"工具 '{tool_name}' 不存在",
            )
            return {
                "todo_list": updated_list,
                "error_info": f"工具 '{tool_name}' 不存在",
                "current_agent": "executor",
            }

    # 无指定工具，使用 LLM 智能选择或直接回答
    if ctx.tools:
        return execute_with_tool_selection(state, current_step, ctx, updated_list)
    else:
        # 无工具可用，使用 LLM 直接回答
        return execute_without_tools(state, current_step, updated_list)


def execute_tool_with_llm(
    state: AgentState,
    step: TodoStep,
    tool: BaseTool,
    ctx: ExecutorContext,
    todo_list: list[TodoStep],
) -> dict:
    """使用 LLM 填充参数并执行工具"""
    settings = get_settings()
    step_id = step["id"]

    # 构建系统提示
    system_prompt = EXECUTOR_SYSTEM_PROMPT.format(
        step_id=step_id,
        step_description=step["description"],
        tool_name=tool.name,
        tools_info=ctx.get_tools_info(),
    )

    # 使用上下文管理器优化消息历史
    context_mgr = get_context_manager(settings.message_token_limit)
    optimized_messages = context_mgr.optimize_context(state)

    # 使用 LLM 绑定工具
    llm = get_llm_with_tools([tool])
    messages = [
        SystemMessage(content=system_prompt),
        *optimized_messages,
        HumanMessage(content=f"请执行步骤：{step['description']}"),
    ]

    try:
        response = llm.invoke(messages)

        # 检查是否有工具调用
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_call = response.tool_calls[0]

            # 执行工具
            tool_result = tool.invoke(tool_call["args"])

            # 更新步骤状态
            updated_list = update_step_status(
                todo_list, step_id, "completed",
                result=str(tool_result),
                progress=100,
            )

            return {
                "messages": [
                    response,
                    ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_call["id"],
                    ),
                ],
                "todo_list": updated_list,
                "current_step": state.get("current_step", 0) + 1,
                "current_agent": "executor",
            }
        else:
            # LLM 直接回答，无工具调用
            updated_list = update_step_status(
                todo_list, step_id, "completed",
                result=response.content,
                progress=100,
            )
            return {
                "messages": [response],
                "todo_list": updated_list,
                "current_step": state.get("current_step", 0) + 1,
                "current_agent": "executor",
            }

    except Exception as e:
        # 执行失败，检查重试
        retry_count = step.get("retry_count", 0) + 1

        if retry_count < settings.max_retries:
            # 可重试
            updated_list = update_step_status(
                todo_list, step_id, "pending",
                error=f"执行失败: {str(e)}，重试 {retry_count}/{settings.max_retries}",
            )
            # 更新重试计数
            for s in updated_list:
                if s["id"] == step_id:
                    s["retry_count"] = retry_count
                    break

            return {
                "todo_list": updated_list,
                "current_agent": "executor",
            }
        else:
            # 重试耗尽
            updated_list = update_step_status(
                todo_list, step_id, "failed",
                error=f"执行失败: {str(e)}，已达最大重试次数",
            )
            return {
                "todo_list": updated_list,
                "error_info": str(e),
                "current_agent": "executor",
            }


def execute_with_tool_selection(
    state: AgentState,
    step: TodoStep,
    ctx: ExecutorContext,
    todo_list: list[TodoStep],
) -> dict:
    """让 LLM 自主选择工具并执行"""
    settings = get_settings()
    step_id = step["id"]

    system_prompt = EXECUTOR_SYSTEM_PROMPT.format(
        step_id=step_id,
        step_description=step["description"],
        tool_name="自动选择",
        tools_info=ctx.get_tools_info(),
    )

    # 使用上下文管理器优化消息历史
    context_mgr = get_context_manager(settings.message_token_limit)
    optimized_messages = context_mgr.optimize_context(state)

    llm = get_llm_with_tools(ctx.tools)
    messages = [
        SystemMessage(content=system_prompt),
        *optimized_messages,
        HumanMessage(content=f"请执行步骤：{step['description']}。如果需要，请选择合适的工具。"),
    ]

    try:
        response = llm.invoke(messages)

        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_call = response.tool_calls[0]
            tool = ctx.get_tool(tool_call["name"])

            if tool:
                tool_result = tool.invoke(tool_call["args"])
                updated_list = update_step_status(
                    todo_list, step_id, "completed",
                    result=str(tool_result),
                    progress=100,
                )
                return {
                    "messages": [
                        response,
                        ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"]),
                    ],
                    "todo_list": updated_list,
                    "current_step": state.get("current_step", 0) + 1,
                    "current_agent": "executor",
                }

        # 无工具调用，使用 LLM 回答
        updated_list = update_step_status(
            todo_list, step_id, "completed",
            result=response.content,
            progress=100,
        )
        return {
            "messages": [response],
            "todo_list": updated_list,
            "current_step": state.get("current_step", 0) + 1,
            "current_agent": "executor",
        }

    except Exception as e:
        updated_list = update_step_status(
            todo_list, step_id, "failed",
            error=str(e),
        )
        return {
            "todo_list": updated_list,
            "error_info": str(e),
            "current_agent": "executor",
        }


def execute_without_tools(
    state: AgentState,
    step: TodoStep,
    todo_list: list[TodoStep],
) -> dict:
    """不使用工具，直接使用 LLM 完成步骤"""
    settings = get_settings()
    step_id = step["id"]
    llm = get_llm()

    # 使用上下文管理器优化消息历史
    context_mgr = get_context_manager(settings.message_token_limit)
    optimized_messages = context_mgr.optimize_context(state)

    messages = [
        SystemMessage(content="你是一个专业的任务执行助手，请根据上下文完成指定的任务步骤。"),
        *optimized_messages,
        HumanMessage(content=f"请完成以下步骤：{step['description']}"),
    ]

    try:
        response = llm.invoke(messages)
        updated_list = update_step_status(
            todo_list, step_id, "completed",
            result=response.content,
            progress=100,
        )
        return {
            "messages": [response],
            "todo_list": updated_list,
            "current_step": state.get("current_step", 0) + 1,
            "current_agent": "executor",
        }
    except Exception as e:
        updated_list = update_step_status(
            todo_list, step_id, "failed",
            error=str(e),
        )
        return {
            "todo_list": updated_list,
            "error_info": str(e),
            "current_agent": "executor",
        }


def should_continue(state: AgentState) -> str:
    """判断是否继续执行"""
    current_step = state.get("current_step", 0)
    todo_list = state.get("todo_list", [])
    final_status = state.get("final_status")

    if final_status in ["failed", "waiting_input"]:
        return "end"

    if current_step >= len(todo_list):
        return "end"

    return "continue"


def build_executor_graph(tools: list[BaseTool] | None = None) -> StateGraph:
    """构建 Executor SubGraph"""
    builder = StateGraph(AgentState)

    # 使用闭包传递 tools
    def executor_with_tools(state: AgentState) -> dict:
        return executor_node(state, tools)

    builder.add_node("executor", executor_with_tools)

    builder.add_edge(START, "executor")
    builder.add_conditional_edges(
        "executor",
        should_continue,
        {
            "continue": "executor",
            "end": END,
        },
    )

    return builder.compile()
