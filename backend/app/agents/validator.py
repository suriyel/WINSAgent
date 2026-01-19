"""
Validator SubGraph - 结果校验Agent
负责：结果判定、错误归因、状态说明
"""

from langchain_core.messages import SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from .state import AgentState
from .llm import get_llm


VALIDATOR_SYSTEM_PROMPT = """你是一个专业的结果校验专家。你的职责是：
1. 验证任务执行结果是否符合预期
2. 识别失败原因并定位到具体步骤
3. 使用业务语言生成状态说明

请检查任务执行结果，并给出以下判断：
1. 整体执行状态：成功/失败/部分成功
2. 如有失败，说明具体原因和建议
3. 生成用户可理解的执行总结
"""


def validator_node(state: AgentState) -> dict:
    """Validator 节点 - 校验执行结果"""
    llm = get_llm()

    todo_list = state.get("todo_list", [])
    error_info = state.get("error_info")

    # 统计执行结果
    completed = sum(1 for s in todo_list if s["status"] == "completed")
    failed = sum(1 for s in todo_list if s["status"] == "failed")
    total = len(todo_list)

    # 构建校验消息
    status_summary = f"""
任务执行统计：
- 总步骤数：{total}
- 已完成：{completed}
- 失败：{failed}

步骤详情：
"""
    for step in todo_list:
        status_icon = {
            "completed": "✅",
            "failed": "❌",
            "running": "🔄",
            "pending": "⏳",
        }.get(step["status"], "❓")
        status_summary += f"{status_icon} {step['description']}"
        if step.get("error"):
            status_summary += f" - 错误: {step['error']}"
        status_summary += "\n"

    if error_info:
        status_summary += f"\n错误信息：{error_info}"

    messages = [
        SystemMessage(content=VALIDATOR_SYSTEM_PROMPT),
        *state["messages"],
        SystemMessage(content=status_summary),
    ]

    response = llm.invoke(messages)

    # 判定最终状态
    if failed > 0:
        final_status = "failed"
    elif completed == total:
        final_status = "success"
    else:
        final_status = "running"

    return {
        "messages": [AIMessage(content=response.content)],
        "final_status": final_status,
        "current_agent": "validator",
    }


def build_validator_graph() -> StateGraph:
    """构建 Validator SubGraph"""
    builder = StateGraph(AgentState)

    builder.add_node("validator", validator_node)

    builder.add_edge(START, "validator")
    builder.add_edge("validator", END)

    return builder.compile()
