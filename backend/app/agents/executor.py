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


EXECUTOR_SYSTEM_PROMPT = """你是任务执行专家。根据步骤描述调用工具完成任务。

当前步骤: {step_description}
{tool_hint}

执行规则:
1. 从对话上下文推断工具参数
2. 参数不完整时，使用合理默认值
3. 无需工具时直接给出结果
"""


class ExecutorContext:
    """执行器上下文"""

    def __init__(self, tools: list[BaseTool] | None = None):
        self.tools = tools or ToolRegistry.get_all()
        self.tool_map = {tool.name: tool for tool in self.tools}

    def get_tool(self, name: str) -> BaseTool | None:
        return self.tool_map.get(name)


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


def annotation_to_field_type(annotation) -> tuple[str, dict]:
    """
    将 Python 类型注解转换为表单字段类型
    返回: (field_type, extra_info)
    """
    import typing
    from typing import get_origin, get_args

    origin = get_origin(annotation)

    # 基础类型
    if annotation == bool:
        return "switch", {}
    elif annotation == int or annotation == float:
        return "number", {}
    elif annotation == str:
        return "text", {}

    # Optional[T] -> T 可选
    if origin is typing.Union:
        args = get_args(annotation)
        # Optional[X] 是 Union[X, None]
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            return annotation_to_field_type(non_none_args[0])

    # List[T]
    if origin is list:
        args = get_args(annotation)
        if args:
            item_type, item_extra = annotation_to_field_type(args[0])
            return "array", {"item_type": item_type, "item_extra": item_extra}
        return "array", {"item_type": "text", "item_extra": {}}

    # Dict[K, V] 或自定义类型 -> object
    if origin is dict:
        return "object", {}

    # Pydantic model 或其他复杂类型
    if hasattr(annotation, "model_fields"):
        return "object", {"model": annotation}

    # 默认文本
    return "text", {}


def generate_field_from_annotation(
    field_name: str,
    annotation,
    field_info,
    depth: int = 0
) -> PendingConfigField:
    """
    从类型注解生成表单字段，支持嵌套和集合
    """
    field_type, extra = annotation_to_field_type(annotation)

    base_field = {
        "name": field_name,
        "label": field_info.description or field_name if field_info else field_name,
        "field_type": field_type,
        "required": field_info.is_required() if field_info else False,
        "default": field_info.default if field_info and field_info.default is not None else None,
        "options": None,
        "placeholder": f"请输入{field_info.description or field_name}" if field_info else None,
        "description": field_info.description if field_info else None,
        "children": None,
        "item_type": None,
    }

    # 处理数组类型
    if field_type == "array" and depth < 3:  # 限制嵌套深度
        item_field_type = extra.get("item_type", "text")
        item_extra = extra.get("item_extra", {})

        # 如果数组元素是对象类型
        if item_field_type == "object" and "model" in item_extra:
            item_model = item_extra["model"]
            item_children = []
            for sub_name, sub_info in item_model.model_fields.items():
                sub_field = generate_field_from_annotation(
                    sub_name, sub_info.annotation, sub_info, depth + 1
                )
                item_children.append(sub_field)
            base_field["item_type"] = {
                "name": "_item",
                "label": "项目",
                "field_type": "object",
                "required": True,
                "default": None,
                "options": None,
                "placeholder": None,
                "description": None,
                "children": item_children,
                "item_type": None,
            }
        else:
            base_field["item_type"] = {
                "name": "_item",
                "label": "项目",
                "field_type": item_field_type,
                "required": True,
                "default": None,
                "options": None,
                "placeholder": None,
                "description": None,
                "children": None,
                "item_type": None,
            }

    # 处理对象类型
    elif field_type == "object" and "model" in extra and depth < 3:
        model = extra["model"]
        children = []
        for sub_name, sub_info in model.model_fields.items():
            sub_field = generate_field_from_annotation(
                sub_name, sub_info.annotation, sub_info, depth + 1
            )
            children.append(sub_field)
        base_field["children"] = children

    return PendingConfigField(**base_field)


def generate_config_fields_from_tool(tool: BaseTool) -> list[PendingConfigField]:
    """从工具 Schema 生成配置表单字段，支持嵌套和集合类型"""
    fields = []
    if not tool.args_schema:
        return fields

    for field_name, field_info in tool.args_schema.model_fields.items():
        field = generate_field_from_annotation(
            field_name, field_info.annotation, field_info
        )
        fields.append(field)

    return fields


def check_missing_params(tool: BaseTool, provided_args: dict) -> list[PendingConfigField]:
    """
    检查工具调用缺失的必需参数
    返回缺失参数的表单字段列表
    """
    missing_fields = []
    if not tool.args_schema:
        return missing_fields

    for field_name, field_info in tool.args_schema.model_fields.items():
        if field_info.is_required() and field_name not in provided_args:
            field = generate_field_from_annotation(
                field_name, field_info.annotation, field_info
            )
            missing_fields.append(field)

    return missing_fields


def tool_requires_approval(tool_name: str, settings) -> bool:
    """检查工具是否需要用户授权"""
    if settings.require_approval_for_all_tools:
        return True
    return tool_name in settings.tools_require_approval


def create_authorization_config(
    step_id: str,
    tool: BaseTool,
    tool_args: dict,
) -> dict:
    """创建授权场景的 PendingConfig"""
    return {
        "step_id": step_id,
        "title": f"工具授权: {tool.name}",
        "description": f"即将执行 {tool.name}，请确认是否授权。\n\n{tool.description}",
        "fields": generate_config_fields_from_tool(tool),
        "values": tool_args,
        "interrupt_type": "authorization",
        "tool_name": tool.name,
        "tool_args": tool_args,
    }


def create_param_required_config(
    step_id: str,
    tool: BaseTool,
    missing_fields: list[PendingConfigField],
    partial_args: dict,
) -> dict:
    """创建参数缺失场景的 PendingConfig"""
    return {
        "step_id": step_id,
        "title": f"参数补充: {tool.name}",
        "description": f"工具 {tool.name} 缺少必需参数，请补充。",
        "fields": missing_fields,
        "values": partial_args,
        "interrupt_type": "param_required",
        "tool_name": tool.name,
        "tool_args": partial_args,
    }


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
                "fields": [{
                    "name": "user_response",
                    "label": "您的回答",
                    "field_type": "textarea",
                    "required": True,
                    "default": None,
                    "options": None,
                    "placeholder": "请输入您的回答...",
                    "description": current_step["description"],
                    "children": None,
                    "item_type": None,
                }],
                "values": {},
                "interrupt_type": "param_required",
                "tool_name": "user_input",
                "tool_args": {},
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


def execute_tool_directly(
    state: AgentState,
    step: TodoStep,
    tool: BaseTool,
    tool_args: dict,
    todo_list: list[TodoStep],
    ai_response=None,
    tool_call_id: str | None = None,
) -> dict:
    """直接执行工具（HITL 恢复后或无需授权时调用）"""
    settings = get_settings()
    step_id = step["id"]

    try:
        # 执行工具
        tool_result = tool.invoke(tool_args)

        # 更新步骤状态
        updated_list = update_step_status(
            todo_list, step_id, "completed",
            result=str(tool_result),
            progress=100,
        )

        messages_to_add = []
        if ai_response:
            messages_to_add.append(ai_response)
        if tool_call_id:
            messages_to_add.append(ToolMessage(
                content=str(tool_result),
                tool_call_id=tool_call_id,
            ))
        else:
            messages_to_add.append(AIMessage(content=f"工具执行结果: {tool_result}"))

        return {
            "messages": messages_to_add,
            "todo_list": updated_list,
            "current_step": state.get("current_step", 0) + 1,
            "current_agent": "executor",
            "pending_config": None,
            "final_status": "running",
        }

    except Exception as e:
        # 执行失败
        retry_count = step.get("retry_count", 0) + 1

        if retry_count < settings.max_retries:
            updated_list = update_step_status(
                todo_list, step_id, "pending",
                error=f"执行失败: {str(e)}，重试 {retry_count}/{settings.max_retries}",
            )
            for s in updated_list:
                if s["id"] == step_id:
                    s["retry_count"] = retry_count
                    break
            return {
                "todo_list": updated_list,
                "current_agent": "executor",
            }
        else:
            updated_list = update_step_status(
                todo_list, step_id, "failed",
                error=f"执行失败: {str(e)}，已达最大重试次数",
            )
            return {
                "todo_list": updated_list,
                "error_info": str(e),
                "current_agent": "executor",
            }


def check_hitl_resume(state: AgentState) -> tuple[bool, dict | None]:
    """
    检查是否从 HITL 中断恢复
    返回: (是否已恢复, 用户提交的数据)
    """
    messages = state.get("messages", [])
    if not messages:
        return False, None

    last_msg = messages[-1]
    content = str(last_msg.content) if hasattr(last_msg, 'content') else ""

    # 检查授权通过
    if content.startswith("HITL_APPROVED:"):
        data_str = content.replace("HITL_APPROVED:", "")
        try:
            return True, {"action": "approve", "data": json.loads(data_str)}
        except:
            return True, {"action": "approve", "data": {}}

    # 检查编辑后提交
    if content.startswith("HITL_EDITED:"):
        data_str = content.replace("HITL_EDITED:", "")
        try:
            return True, {"action": "edit", "data": json.loads(data_str)}
        except:
            return True, {"action": "edit", "data": {}}

    # 检查参数补充
    if content.startswith("HITL_PARAM:"):
        data_str = content.replace("HITL_PARAM:", "")
        try:
            return True, {"action": "param", "data": json.loads(data_str)}
        except:
            return True, {"action": "param", "data": {}}

    return False, None


def execute_tool_with_llm(
    state: AgentState,
    step: TodoStep,
    tool: BaseTool,
    ctx: ExecutorContext,
    todo_list: list[TodoStep],
) -> dict:
    """使用 LLM 填充参数并执行工具，支持 HITL"""
    settings = get_settings()
    step_id = step["id"]

    # 检查是否从 HITL 恢复
    resumed, resume_data = check_hitl_resume(state)
    if resumed and resume_data:
        print(f"[EXECUTOR] Resumed from HITL: {resume_data}")
        # 使用用户提供/确认的参数执行工具
        tool_args = resume_data.get("data", {})
        return execute_tool_directly(state, step, tool, tool_args, todo_list)

    # 构建系统提示
    system_prompt = EXECUTOR_SYSTEM_PROMPT.format(
        step_description=step["description"],
        tool_hint=f"指定工具: {tool.name}",
    )

    # 使用上下文管理器优化消息历史
    context_mgr = get_context_manager(settings.message_token_limit)
    optimized_messages = context_mgr.optimize_context(state)

    # 使用 LLM 绑定工具
    llm = get_llm_with_tools([tool])
    messages = [
        SystemMessage(content=system_prompt),
        *optimized_messages,
    ]

    try:
        response = llm.invoke(messages)

        # 检查是否有工具调用
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_call = response.tool_calls[0]
            tool_args = tool_call["args"]

            # 1. 检查参数缺失
            missing_fields = check_missing_params(tool, tool_args)
            if missing_fields:
                print(f"[EXECUTOR] Missing params for {tool.name}: {[f['name'] for f in missing_fields]}")
                pending_config = create_param_required_config(
                    step_id, tool, missing_fields, tool_args
                )
                return {
                    "messages": [response],
                    "todo_list": todo_list,
                    "pending_config": pending_config,
                    "final_status": "waiting_input",
                    "current_agent": "executor",
                }

            # 2. 检查是否需要授权
            if tool_requires_approval(tool.name, settings):
                print(f"[EXECUTOR] Tool {tool.name} requires approval")
                pending_config = create_authorization_config(step_id, tool, tool_args)
                return {
                    "messages": [response],
                    "todo_list": todo_list,
                    "pending_config": pending_config,
                    "final_status": "waiting_input",
                    "current_agent": "executor",
                }

            # 3. 直接执行工具
            return execute_tool_directly(state, step, tool, tool_args, todo_list, response, tool_call["id"])

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
        step_description=step["description"],
        tool_hint="请根据任务需要选择合适的工具",
    )

    # 使用上下文管理器优化消息历史
    context_mgr = get_context_manager(settings.message_token_limit)
    optimized_messages = context_mgr.optimize_context(state)

    llm = get_llm_with_tools(ctx.tools)
    messages = [
        SystemMessage(content=system_prompt),
        *optimized_messages,
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

    system_prompt = EXECUTOR_SYSTEM_PROMPT.format(
        step_description=step["description"],
        tool_hint="无可用工具，请直接给出结果",
    )
    messages = [
        SystemMessage(content=system_prompt),
        *optimized_messages,
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
