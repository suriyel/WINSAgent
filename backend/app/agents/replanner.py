"""
Replanner Agent - 动态重规划
负责：在步骤失败时生成替代方案、调整执行计划
"""

import json
import re
from typing import Any, Literal

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from .state import AgentState, TodoStep, ReplanContext, create_todo_step
from .llm import get_llm
from .context_manager import get_context_manager
from app.tools.base import ToolRegistry
from app.config import get_settings


REPLANNER_SYSTEM_PROMPT = """你是一个任务重规划专家。当任务执行遇到问题时，你需要分析失败原因并生成替代方案。

## 触发原因
{trigger_reason}

## 失败步骤信息
步骤ID：{failed_step_id}
错误信息：{failed_step_error}

## 已完成步骤（需保留这些结果）
{completed_steps}

## 原始用户意图
{original_intent}

## 剩余待执行步骤
{remaining_steps}

## 可用工具列表
{available_tools}

## 重规划策略选项
1. **replace_failed**: 用替代方法替换失败的步骤
2. **alternative_approach**: 从失败点重新设计执行方案
3. **skip_failed**: 跳过失败步骤，继续执行后续（仅当失败步骤非关键时）
4. **abort**: 无法恢复，终止任务并报告原因

## 输出格式要求
请严格按照以下JSON格式输出重规划结果，不要包含任何额外文字：
```json
{{
  "strategy": "replace_failed|alternative_approach|skip_failed|abort",
  "explanation": "选择该策略的原因说明",
  "new_steps": [
    {{
      "id": "step_new_1",
      "description": "新步骤描述",
      "tool_name": "工具名称或null",
      "depends_on": []
    }}
  ],
  "steps_to_skip": ["要跳过的步骤ID列表"]
}}
```

## 重规划原则
- 保留已完成步骤的成果，不要重复执行
- 新步骤ID应以 step_replan_{replan_count}_ 为前缀，如 step_replan_1_1
- 如果失败是由于参数问题，考虑调整参数而非更换工具
- 如果工具不可用，考虑使用替代工具或手动方式
- abort 策略仅在确实无法完成任务时使用
- 每次重规划最多添加 5 个新步骤
"""


# 触发原因的中文描述
TRIGGER_REASON_DESC = {
    "max_retries_exceeded": "步骤执行多次重试后仍然失败",
    "goal_achieved_early": "目标已提前达成",
    "alternative_approach_needed": "当前方法无法继续，需要替代方案",
    "user_requested": "用户主动请求重新规划",
    "dependency_failed": "依赖的前置步骤执行失败",
}


def get_available_tools_description() -> str:
    """获取可用工具的描述列表"""
    tools = ToolRegistry.get_all()
    if not tools:
        return "当前无可用工具"

    tool_descriptions = []
    for t in tools:
        tool_descriptions.append(f"- {t.name}: {t.description}")
    return "\n".join(tool_descriptions)


def parse_replan_response(content: str) -> dict[str, Any] | None:
    """解析 LLM 返回的重规划结果"""
    # 尝试提取 JSON 代码块
    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_str = content

    try:
        json_str = json_str.strip()
        if json_str.startswith('```'):
            json_str = json_str[3:]
        if json_str.endswith('```'):
            json_str = json_str[:-3]

        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def build_completed_steps_summary(completed_results: list[dict]) -> str:
    """构建已完成步骤摘要"""
    if not completed_results:
        return "无已完成步骤"

    lines = []
    for result in completed_results:
        lines.append(
            f"- [{result['step_id']}] {result['description']}: {result['result'][:100]}..."
            if len(result.get('result', '')) > 100
            else f"- [{result['step_id']}] {result['description']}: {result.get('result', '无结果')}"
        )
    return "\n".join(lines)


def build_remaining_steps_summary(
    todo_list: list[TodoStep],
    remaining_ids: list[str],
) -> str:
    """构建剩余步骤摘要"""
    if not remaining_ids:
        return "无剩余步骤"

    lines = []
    step_map = {s["id"]: s for s in todo_list}
    for step_id in remaining_ids:
        step = step_map.get(step_id)
        if step:
            tool_info = f" (工具: {step['tool_name']})" if step.get("tool_name") else ""
            lines.append(f"- [{step_id}] {step['description']}{tool_info}")
    return "\n".join(lines)


def merge_replan_into_todo_list(
    todo_list: list[TodoStep],
    replan_result: dict,
    failed_step_id: str | None,
) -> list[TodoStep]:
    """将重规划结果合并到 TODO 列表

    Args:
        todo_list: 当前任务列表
        replan_result: LLM 返回的重规划结果
        failed_step_id: 失败步骤ID

    Returns:
        合并后的新任务列表
    """
    strategy = replan_result.get("strategy", "abort")
    new_steps_data = replan_result.get("new_steps", [])
    steps_to_skip = set(replan_result.get("steps_to_skip", []))

    updated_list = []

    for step in todo_list:
        step_id = step["id"]

        # 处理需要跳过的步骤
        if step_id in steps_to_skip and step["status"] == "pending":
            updated_list.append({
                **step,
                "status": "skipped",
                "result": "重规划时跳过",
            })
            continue

        # 保留已完成的步骤
        if step["status"] == "completed":
            updated_list.append(step)
            continue

        # 处理失败步骤
        if step_id == failed_step_id:
            if strategy == "replace_failed":
                # 标记为跳过，用新步骤替代
                updated_list.append({
                    **step,
                    "status": "skipped",
                    "result": "重规划：使用替代方案",
                })
            elif strategy == "skip_failed":
                # 跳过失败步骤
                updated_list.append({
                    **step,
                    "status": "skipped",
                    "result": "重规划：跳过非关键步骤",
                })
            else:
                # 保持失败状态
                updated_list.append(step)
            continue

        # 其他步骤保持原样
        updated_list.append(step)

    # 添加新步骤
    if strategy in ("replace_failed", "alternative_approach"):
        for step_data in new_steps_data[:5]:  # 限制最多5个新步骤
            new_step = create_todo_step(
                step_id=step_data.get("id", f"step_new_{len(updated_list)}"),
                description=step_data.get("description", "新步骤"),
                tool_name=step_data.get("tool_name"),
                depends_on=step_data.get("depends_on", []),
            )
            updated_list.append(new_step)

    return updated_list


def replanner_node(state: AgentState) -> dict:
    """Replanner 节点 - 生成重规划方案"""
    settings = get_settings()
    llm = get_llm()

    replan_context: ReplanContext | None = state.get("replan_context")
    todo_list = state.get("todo_list", [])

    if not replan_context:
        # 无重规划上下文，返回原状态
        return {
            "current_agent": "replanner",
            "replan_context": None,
        }

    # 检查重规划次数限制
    replan_count = replan_context.get("replan_count", 0)
    if replan_count >= settings.max_replans:
        # 超过重规划次数限制
        return {
            "messages": [AIMessage(
                content=f"已达到最大重规划次数限制（{settings.max_replans}次），无法继续重规划。"
            )],
            "current_agent": "replanner",
            "replan_context": None,
            "final_status": "failed",
            "error_info": "重规划次数超限",
        }

    # 构建提示参数
    trigger_reason = replan_context.get("trigger_reason", "unknown")
    trigger_desc = TRIGGER_REASON_DESC.get(trigger_reason, trigger_reason)

    completed_steps_summary = build_completed_steps_summary(
        replan_context.get("completed_results", [])
    )
    remaining_steps_summary = build_remaining_steps_summary(
        todo_list, replan_context.get("remaining_steps", [])
    )

    system_prompt = REPLANNER_SYSTEM_PROMPT.format(
        trigger_reason=trigger_desc,
        failed_step_id=replan_context.get("failed_step_id", "N/A"),
        failed_step_error=replan_context.get("failed_step_error", "N/A"),
        completed_steps=completed_steps_summary,
        original_intent=replan_context.get("original_intent", ""),
        remaining_steps=remaining_steps_summary,
        available_tools=get_available_tools_description(),
        replan_count=replan_count + 1,
    )

    # 使用上下文管理器优化消息历史
    context_mgr = get_context_manager(settings.message_token_limit)
    optimized_messages = context_mgr.optimize_context(state)

    messages = [
        SystemMessage(content=system_prompt),
        *optimized_messages,
        HumanMessage(content="请分析失败原因并生成重规划方案。"),
    ]

    try:
        response = llm.invoke(messages)
        content = response.content

        # 解析响应
        replan_result = parse_replan_response(content)

        if not replan_result:
            # 解析失败，终止任务
            return {
                "messages": [AIMessage(content="重规划响应解析失败，无法继续。")],
                "current_agent": "replanner",
                "replan_context": None,
                "final_status": "failed",
                "error_info": "重规划解析失败",
            }

        strategy = replan_result.get("strategy", "abort")
        explanation = replan_result.get("explanation", "")

        # 处理 abort 策略
        if strategy == "abort":
            return {
                "messages": [AIMessage(
                    content=f"**重规划结论：无法继续执行**\n\n{explanation}"
                )],
                "current_agent": "replanner",
                "replan_context": None,
                "final_status": "failed",
                "error_info": explanation,
            }

        # 合并重规划结果到 TODO 列表
        updated_todo_list = merge_replan_into_todo_list(
            todo_list,
            replan_result,
            replan_context.get("failed_step_id"),
        )

        # 找到下一个待执行步骤的索引
        next_step_idx = 0
        for i, step in enumerate(updated_todo_list):
            if step["status"] == "pending":
                next_step_idx = i
                break

        # 生成用户可见的重规划说明
        strategy_desc = {
            "replace_failed": "使用替代方案",
            "alternative_approach": "采用新的执行路径",
            "skip_failed": "跳过非关键步骤",
        }.get(strategy, strategy)

        new_steps_count = len(replan_result.get("new_steps", []))
        skip_count = len(replan_result.get("steps_to_skip", []))

        summary_parts = [f"**重规划完成** - 策略：{strategy_desc}"]
        if new_steps_count > 0:
            summary_parts.append(f"新增 {new_steps_count} 个步骤")
        if skip_count > 0:
            summary_parts.append(f"跳过 {skip_count} 个步骤")
        summary_parts.append(f"\n\n{explanation}")

        return {
            "messages": [AIMessage(content="\n".join(summary_parts))],
            "todo_list": updated_todo_list,
            "current_step": next_step_idx,
            "current_agent": "replanner",
            "replan_context": None,  # 清除重规划上下文
            "final_status": "running",
        }

    except Exception as e:
        print(f"[REPLANNER] Error: {e}")
        return {
            "messages": [AIMessage(content=f"重规划过程出错：{str(e)}")],
            "current_agent": "replanner",
            "replan_context": None,
            "final_status": "failed",
            "error_info": str(e),
        }
