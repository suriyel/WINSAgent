"""ChartDataMiddleware - 提取图表对比数据，减少 LLM 上下文，全量数据通过 SSE 发送前端.

对工具返回的 [CHART_DATA]...[/CHART_DATA] 块：
- 从 ToolMessage.content 中剥离 JSON 块，替换为文本摘要（供 LLM 使用）
- 完整结构化数据存入 ToolMessage.additional_kwargs["chart_data"]
- event_mapper 检测后发射独立的 chart.data SSE 事件
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.typing import ContextT

logger = logging.getLogger(__name__)

CHART_TAG_START = "[CHART_DATA]"
CHART_TAG_END = "[/CHART_DATA]"

_CHART_PATTERN = re.compile(
    rf"{re.escape(CHART_TAG_START)}(.*?){re.escape(CHART_TAG_END)}",
    re.DOTALL,
)


class ChartDataMiddleware(AgentMiddleware[AgentState, ContextT]):
    """拦截工具结果中的 [CHART_DATA] 块，提取图表数据并注入 additional_kwargs.

    使用 wrap_tool_call 钩子，对任何返回 [CHART_DATA] 标记的工具透明生效。
    """

    name: str = "chart_data"

    def wrap_tool_call(
        self,
        request: dict[str, Any],
        handler: Any,
    ) -> ToolMessage:
        result = handler(request)

        if not isinstance(result, ToolMessage):
            return result

        content = result.content
        if not isinstance(content, str) or CHART_TAG_START not in content:
            return result

        chart_data, cleaned_content = self._extract_chart_data(content)

        if chart_data is None:
            return result

        logger.info(
            "ChartDataMiddleware: extracted chart_data with %d cells",
            len(chart_data.get("data", {}).get("cells", [])),
        )

        return ToolMessage(
            content=cleaned_content,
            tool_call_id=result.tool_call_id,
            name=result.name,
            status=getattr(result, "status", "success"),
            additional_kwargs={
                **result.additional_kwargs,
                "chart_data": chart_data,
            },
        )

    @staticmethod
    def _extract_chart_data(
        content: str,
    ) -> tuple[dict | None, str]:
        """提取第一个 [CHART_DATA] JSON 块，返回 (解析后数据, 清理后内容)."""
        match = _CHART_PATTERN.search(content)
        if not match:
            return None, content

        json_text = match.group(1).strip()
        try:
            chart_data = json.loads(json_text)
        except json.JSONDecodeError:
            logger.warning("ChartDataMiddleware: failed to parse chart JSON")
            return None, content

        # 从内容中移除 [CHART_DATA] 块，LLM 只看到文本摘要
        cleaned = content.replace(match.group(0), "").strip()
        return chart_data, cleaned
