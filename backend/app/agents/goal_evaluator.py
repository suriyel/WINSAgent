"""
Goal Evaluator - 目标达成评估
负责：检测用户目标是否提前达成，以便跳过后续不必要的步骤
"""

import json
import re
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage

from .state import AgentState, TodoStep
from .llm import get_llm
from app.config import get_settings


GOAL_EVALUATOR_PROMPT = """你是一个任务目标评估专家。你的职责是判断用户的原始目标是否已经通过当前步骤的执行结果达成。

## 原始用户意图
{intent}

## 已完成步骤
{completed_steps}

## 当前步骤执行结果
步骤描述：{current_step_description}
执行结果：{current_result}

## 剩余待执行步骤
{remaining_steps}

## 评估要求
请分析当前步骤的执行结果，判断：
1. 用户的原始目标是否已经完全达成
2. 剩余步骤是否还有必要执行

请严格按照以下JSON格式输出，不要包含任何额外文字：
```json
{{
  "goal_achieved": true/false,
  "completion_percentage": 0-100,
  "explanation": "判断依据说明"
}}
```

## 判断原则
- 只有当用户的核心需求已被满足时，才判定 goal_achieved 为 true
- 如果剩余步骤是可选的美化/优化步骤，且核心功能已完成，可以判定目标达成
- 如果剩余步骤是必要的验证/确认步骤，不应跳过
- completion_percentage 表示整体任务完成度（0-100）
"""


# 目标达成指示词 - 用于启发式判断是否需要进行目标评估
GOAL_INDICATORS = [
    "完成", "成功", "已获取", "已生成", "已创建", "已保存",
    "done", "success", "completed", "achieved", "finished",
    "created", "generated", "saved", "obtained",
]


def should_evaluate_goal(step: TodoStep, state: AgentState) -> bool:
    """判断是否需要进行目标评估（启发式检查）

    Args:
        step: 当前完成的步骤
        state: Agent 状态

    Returns:
        是否需要进行目标评估
    """
    result = step.get("result", "")
    if not result:
        return False

    result_lower = result.lower()

    # 1. 检查结果是否包含成功指示词
    has_success_indicator = any(
        indicator in result_lower for indicator in GOAL_INDICATORS
    )

    # 2. 检查是否有剩余步骤（如果没有，则无需评估）
    todo_list = state.get("todo_list", [])
    current_step_idx = state.get("current_step", 0)
    has_remaining_steps = current_step_idx < len(todo_list) - 1

    # 3. 只有当有成功指示且有剩余步骤时才评估
    return has_success_indicator and has_remaining_steps


def evaluate_goal_completion(
    state: AgentState,
    current_step: TodoStep,
) -> dict[str, Any]:
    """评估用户目标是否已达成

    Args:
        state: Agent 状态
        current_step: 当前完成的步骤

    Returns:
        评估结果: {"goal_achieved": bool, "completion_percentage": int, "explanation": str}
    """
    settings = get_settings()
    llm = get_llm()

    todo_list = state.get("todo_list", [])
    parsed_intent = state.get("parsed_intent", "")

    # 构建已完成步骤摘要
    completed_steps = []
    for step in todo_list:
        if step["status"] == "completed" and step["id"] != current_step["id"]:
            result_summary = step.get("result", "")[:150] if step.get("result") else "无结果"
            completed_steps.append(f"- {step['description']}: {result_summary}")

    completed_steps_text = "\n".join(completed_steps) if completed_steps else "无已完成步骤"

    # 构建剩余步骤摘要
    remaining_steps = []
    found_current = False
    for step in todo_list:
        if step["id"] == current_step["id"]:
            found_current = True
            continue
        if found_current and step["status"] == "pending":
            remaining_steps.append(f"- {step['description']}")

    remaining_steps_text = "\n".join(remaining_steps) if remaining_steps else "无剩余步骤"

    # 构建提示
    prompt = GOAL_EVALUATOR_PROMPT.format(
        intent=parsed_intent or "未知意图",
        completed_steps=completed_steps_text,
        current_step_description=current_step["description"],
        current_result=current_step.get("result", "")[:500],
        remaining_steps=remaining_steps_text,
    )

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content="请评估当前目标是否已达成。"),
    ]

    try:
        response = llm.invoke(messages)
        content = response.content

        # 解析 JSON 响应
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = content

        result = json.loads(json_str.strip())

        return {
            "goal_achieved": result.get("goal_achieved", False),
            "completion_percentage": result.get("completion_percentage", 0),
            "explanation": result.get("explanation", ""),
        }

    except (json.JSONDecodeError, Exception) as e:
        print(f"[GOAL_EVALUATOR] Failed to parse response: {e}")
        # 解析失败时保守处理，不跳过步骤
        return {
            "goal_achieved": False,
            "completion_percentage": 0,
            "explanation": f"评估失败: {str(e)}",
        }
