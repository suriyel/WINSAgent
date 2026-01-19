"""
Executor SubGraph - 任务执行Agent
负责：Tool选择、参数填充、执行调度、重试处理
"""

from typing import Any
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from .state import AgentState, TodoStep
from .llm import get_llm_with_tools


EXECUTOR_SYSTEM_PROMPT = """你是一个专业的任务执行专家。你的职责是：
1. 根据任务步骤选择合适的工具
2. 准确填充工具所需参数
3. 执行工具调用并处理结果
4. 处理错误和重试逻辑

当前任务步骤信息会通过上下文提供给你。

注意：
- 只执行当前步骤，不要跳过或合并步骤
- 如果参数不确定，可以请求用户确认
- 工具调用失败时，分析原因并决定是否重试
"""


class ExecutorContext:
    """执行器上下文"""

    def __init__(self, tools: list[BaseTool]):
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}

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


def executor_node(state: AgentState, tools: list[BaseTool] | None = None) -> dict:
    """Executor 节点 - 执行当前步骤"""
    current_step = get_current_step(state)

    if not current_step:
        # 所有步骤已完成
        return {
            "current_agent": "executor",
            "final_status": "success",
        }

    todo_list = state.get("todo_list", [])

    # 检查依赖
    if not check_dependencies_met(current_step, todo_list):
        return {
            "error_info": f"步骤 {current_step['id']} 的依赖尚未完成",
            "current_agent": "executor",
        }

    # 更新步骤状态为运行中
    updated_list = update_step_status(
        todo_list, current_step["id"], "running", progress=10
    )

    # 如果需要用户输入，触发中断
    if current_step.get("tool_name") == "user_input":
        # 触发 Human-in-the-Loop
        response = interrupt(
            {
                "action": "request_input",
                "step_id": current_step["id"],
                "message": current_step["description"],
            }
        )
        return {
            "todo_list": updated_list,
            "pending_config": {
                "step_id": current_step["id"],
                "title": "需要您的输入",
                "description": current_step["description"],
                "fields": [],
                "values": {},
            },
            "final_status": "waiting_input",
            "current_agent": "executor",
        }

    # 执行工具调用
    tool_name = current_step.get("tool_name")
    if tool_name and tools:
        llm = get_llm_with_tools(tools)
        messages = [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT),
            *state["messages"],
        ]

        try:
            response = llm.invoke(messages)
            # 处理工具调用
            updated_list = update_step_status(
                updated_list,
                current_step["id"],
                "completed",
                result=str(response.content),
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
                updated_list,
                current_step["id"],
                "failed",
                error=str(e),
            )
            return {
                "todo_list": updated_list,
                "error_info": str(e),
                "current_agent": "executor",
            }

    # 无工具调用，直接标记完成
    updated_list = update_step_status(
        updated_list,
        current_step["id"],
        "completed",
        result="步骤已完成",
        progress=100,
    )

    return {
        "todo_list": updated_list,
        "current_step": state.get("current_step", 0) + 1,
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
