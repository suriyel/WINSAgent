"""
研究专家 SubAgent

职责:
- 深入调研问题
- 从知识库检索信息
- 综合分析并给出报告
"""

from typing import List, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from app.agents.tools.business import search_knowledge


RESEARCH_SYSTEM_PROMPT = """你是一个专业的研究分析专家。

你的职责是深入调研问题，从知识库中检索相关信息，综合分析后给出全面的研究报告。

## 研究方法

1. **理解问题**
   - 明确研究目标
   - 识别关键问题点
   - 确定研究范围

2. **信息收集**
   - 使用 search_knowledge 工具检索知识库
   - 多角度搜索，覆盖不同关键词
   - 记录所有相关发现

3. **分析整合**
   - 整理收集到的信息
   - 识别模式和关联
   - 评估信息的可靠性和相关性

4. **形成结论**
   - 综合分析结果
   - 给出明确的结论
   - 指出信息的局限性

## 输出格式

### 研究报告

**研究主题:** [主题描述]

**关键发现:**
1. [发现1]
2. [发现2]
...

**详细分析:**

[对各个方面的详细分析]

**信息来源:**
- [来源1]
- [来源2]
...

**结论:**
[综合结论]

**局限性:**
- [信息可能不完整的地方]
- [需要进一步验证的点]

**建议:**
- [基于研究的建议]

---

## 注意事项

- 主动使用 search_knowledge 工具获取信息
- 如果一次搜索结果不足，尝试不同的关键词
- 区分事实和推测
- 保持客观，标注信息来源
- 如果知识库中没有相关信息，明确说明
"""


class ResearchInput(TypedDict):
    """研究专家输入"""
    messages: List[dict]


def create_research_tool(model: BaseChatModel) -> BaseTool:
    """
    创建研究专家工具

    Args:
        model: LLM 模型实例

    Returns:
        作为工具的研究专家 Agent
    """
    # 研究专家可以使用知识库搜索工具
    research_agent = create_react_agent(
        model=model,
        tools=[search_knowledge],
        prompt=RESEARCH_SYSTEM_PROMPT,
    )

    # 转换为工具
    research_tool = research_agent.as_tool(
        name="research_expert",
        description="""研究专家。当需要深入调研某个主题或从知识库获取信息时调用。

使用场景:
- 需要了解某个领域的知识
- 需要查找历史案例或最佳实践
- 需要综合多方信息进行分析

输入: 包含研究问题的消息列表
输出: 详细的研究报告，包括关键发现、分析、结论和建议""",
        arg_types={"messages": List[dict]},
    )

    return research_tool
