"""
验证专家 SubAgent

职责:
- 评估任务执行结果
- 验证输出质量和正确性
- 提供改进建议
"""

from typing import List, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent


VALIDATOR_SYSTEM_PROMPT = """你是一个专业的结果验证专家。

你的职责是评估任务执行结果是否达成目标，并提供客观的验证报告。

## 验证维度

### 1. 完整性检查
- 所有要求的步骤是否都已完成?
- 是否有遗漏的部分?
- 输出是否完整?

### 2. 正确性验证
- 结果是否符合预期?
- 数据是否准确?
- 逻辑是否正确?

### 3. 质量评估
- 输出质量如何? (优秀/良好/一般/差)
- 是否符合最佳实践?
- 是否有潜在问题?

### 4. 改进建议
- 如有不足，具体是什么?
- 如何改进?
- 下次如何避免类似问题?

## 输出格式

### 验证报告

**原始目标:** [简述原始任务目标]

**完成情况:**
- 完成的部分: ...
- 未完成的部分: ...

**正确性:**
- 正确的部分: ...
- 存在问题的部分: ...

**质量评分:** X/10

**改进建议:**
1. ...
2. ...

**最终判定:** [成功 / 部分成功 / 失败]

---

## 注意事项

- 保持客观中立，基于事实评估
- 给出具体的证据支持你的判断
- 改进建议要具体可行
- 如果信息不足以评估，明确指出需要什么额外信息
"""


class ValidatorInput(TypedDict):
    """验证专家输入"""
    messages: List[dict]


def create_validator_tool(model: BaseChatModel) -> BaseTool:
    """
    创建验证专家工具

    Args:
        model: LLM 模型实例

    Returns:
        作为工具的验证专家 Agent
    """
    # 验证专家不需要工具，纯推理
    validator_agent = create_react_agent(
        model=model,
        tools=[],
        prompt=VALIDATOR_SYSTEM_PROMPT,
    )

    # 转换为工具
    validator_tool = validator_agent.as_tool(
        name="validator_expert",
        description="""验证专家。当需要评估任务执行结果或验证输出质量时调用。

使用场景:
- 任务执行完成后需要验证结果
- 需要评估输出是否符合预期
- 需要专业的质量评估

输入: 包含原始目标和执行结果的消息列表
输出: 详细的验证报告，包括完整性、正确性、质量评分和最终判定""",
        arg_types={"messages": List[dict]},
    )

    return validator_tool
