"""
Validator SubGraph - 结果校验Agent
负责：结果判定、错误归因、状态说明
"""

import json
import re
from typing import Any
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

from .state import AgentState, TodoStep
from .llm import get_llm
from .context_manager import get_context_manager
from app.config import get_settings


VALIDATOR_SYSTEM_PROMPT = """你是一个专业的结果校验专家。你的职责是：
1. 验证任务执行结果是否符合用户的原始需求
2. 识别失败原因并定位到具体步骤
3. 生成用户友好的执行总结

## 执行统计
{stats}

## 步骤执行详情
{step_details}

## 原始用户需求
请基于对话历史回顾用户的原始需求。

## 输出要求
请生成一份执行总结报告，包含：
1. **执行结果**: 成功/部分成功/失败
2. **完成情况**: 简要说明完成了什么
3. **问题分析**: 如有失败，分析原因
4. **建议**: 如有需要，给出后续建议

使用清晰简洁的语言，避免技术术语，让用户容易理解。
"""


def build_step_details(todo_list: list[TodoStep]) -> str:
    """构建步骤执行详情"""
    details = []
    for i, step in enumerate(todo_list, 1):
        status_icon = {
            "completed": "✅",
            "failed": "❌",
            "running": "🔄",
            "pending": "⏳",
            "skipped": "⏭️",
        }.get(step["status"], "❓")

        detail = f"{i}. {status_icon} {step['description']}"

        if step.get("result"):
            # 截取结果摘要
            result = step["result"]
            if len(result) > 200:
                result = result[:200] + "..."
            detail += f"\n   结果: {result}"

        if step.get("error"):
            detail += f"\n   错误: {step['error']}"

        details.append(detail)

    return "\n".join(details)


def analyze_failures(todo_list: list[TodoStep]) -> dict[str, Any]:
    """分析失败步骤"""
    failures = []
    for step in todo_list:
        if step["status"] == "failed":
            failures.append({
                "step_id": step["id"],
                "description": step["description"],
                "error": step.get("error", "未知错误"),
                "tool_name": step.get("tool_name"),
            })

    # 错误分类
    error_categories = {}
    for f in failures:
        error = f["error"]
        if "timeout" in error.lower():
            category = "超时"
        elif "not found" in error.lower() or "不存在" in error:
            category = "资源不存在"
        elif "permission" in error.lower() or "权限" in error:
            category = "权限问题"
        elif "connection" in error.lower() or "连接" in error:
            category = "连接问题"
        else:
            category = "其他"

        if category not in error_categories:
            error_categories[category] = []
        error_categories[category].append(f)

    return {
        "failures": failures,
        "error_categories": error_categories,
    }


def validator_node(state: AgentState) -> dict:
    """Validator 节点 - 校验执行结果"""
    settings = get_settings()
    llm = get_llm()

    todo_list = state.get("todo_list", [])
    error_info = state.get("error_info")
    parsed_intent = state.get("parsed_intent", "")
    goal_achieved = state.get("goal_achieved", False)
    goal_evaluation_result = state.get("goal_evaluation_result", "")

    # 统计执行结果
    completed = sum(1 for s in todo_list if s["status"] == "completed")
    failed = sum(1 for s in todo_list if s["status"] == "failed")
    pending = sum(1 for s in todo_list if s["status"] == "pending")
    running = sum(1 for s in todo_list if s["status"] == "running")
    skipped = sum(1 for s in todo_list if s["status"] == "skipped")
    total = len(todo_list)

    # 构建统计信息
    stats = f"""- 总步骤数：{total}
- 已完成：{completed}
- 跳过：{skipped}
- 失败：{failed}
- 进行中：{running}
- 待执行：{pending}"""

    # 如果目标提前达成，添加说明
    if goal_achieved:
        stats += f"\n- 目标提前达成：{goal_evaluation_result}"

    # 构建步骤详情
    step_details = build_step_details(todo_list)

    # 如果有失败，添加失败分析
    if failed > 0:
        failure_analysis = analyze_failures(todo_list)
        step_details += "\n\n## 失败分析\n"
        for category, items in failure_analysis["error_categories"].items():
            step_details += f"- {category}: {len(items)} 个步骤\n"

    if error_info:
        step_details += f"\n系统错误：{error_info}"

    # 构建系统提示
    system_prompt = VALIDATOR_SYSTEM_PROMPT.format(
        stats=stats,
        step_details=step_details,
    )

    # Validator 不需要完整的消息历史，只需要系统提示和总结请求
    # 避免传递包含 tool_calls 的消息，这些消息可能会导致 LLM 格式错误
    final_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="请对以上任务执行结果进行验证和总结。"),
    ]

    response = llm.invoke(final_messages)

    # 判定最终状态（考虑 skipped 步骤）
    finished_count = completed + skipped  # 完成 + 跳过 = 实际处理完毕

    if failed > 0 and completed == 0:
        final_status = "failed"
    elif failed > 0 and completed > 0:
        # 部分成功也标记为 failed，但在消息中说明
        final_status = "failed"
    elif finished_count == total and total > 0:
        # 全部完成（包括跳过的）= 成功
        final_status = "success"
    elif pending > 0 or running > 0:
        final_status = "running"
    else:
        final_status = "success"

    # 构建最终消息
    if goal_achieved and skipped > 0:
        # 目标提前达成
        status_label = "✅ 目标提前达成"
    else:
        status_label = {
            "success": "✅ 任务完成",
            "failed": "❌ 任务失败" if completed == 0 else "⚠️ 部分完成",
            "running": "🔄 执行中",
        }.get(final_status, "❓ 未知状态")

    final_message = f"**{status_label}**\n\n{response.content}"

    return {
        "messages": [AIMessage(content=final_message)],
        "final_status": final_status,
        "current_agent": "validator",
        "pending_config": None,  # 清除待处理配置
        "goal_achieved": False,  # 重置目标达成标记
        "replan_context": None,  # 清除重规划上下文
    }


def build_validator_graph() -> StateGraph:
    """构建 Validator SubGraph"""
    builder = StateGraph(AgentState)

    builder.add_node("validator", validator_node)

    builder.add_edge(START, "validator")
    builder.add_edge("validator", END)

    return builder.compile()
