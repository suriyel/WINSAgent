"""Suggestions Middleware - 从 LLM 响应中解析建议选项并存储到 state."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from pydantic import BaseModel


class Suggestion(BaseModel):
    """单个建议选项."""

    id: str
    text: str
    value: str | None = None


class SuggestionsData(BaseModel):
    """建议选项数据结构."""

    suggestions: list[Suggestion]
    multi_select: bool = False
    prompt: str | None = None


class SuggestionsState(AgentState):
    """扩展的 Agent State，包含 suggestions 字段."""

    suggestions: SuggestionsData | None


class SuggestionsMiddleware(AgentMiddleware[SuggestionsState, ContextT]):
    """从 LLM 响应中解析建议选项的 Middleware.

    支持两种格式：
    1. JSON 代码块: ```suggestions {...} ```
    2. XML 标签: <suggestions>...</suggestions>

    解析后的建议会存储到 state.suggestions 中，
    同时从消息内容中移除建议标记。
    """

    name: str = "suggestions"
    state_schema = SuggestionsState

    def after_model(self, state: SuggestionsState, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """在模型响应后解析并提取建议选项."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_message = messages[-1]

        # 只处理 AI 消息且没有工具调用的情况
        if not isinstance(last_message, AIMessage):
            return None

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return None

        content = last_message.content
        if not content or not isinstance(content, str):
            return None

        # 解析建议选项
        cleaned_content, suggestions_data = self._parse_suggestions(content)

        # 如果没有变化，返回 None
        if cleaned_content == content and suggestions_data is None:
            return None

        # 更新消息内容和 suggestions state
        updated_message = AIMessage(
            content=cleaned_content,
            id=last_message.id,
            response_metadata=getattr(last_message, "response_metadata", {}),
        )

        return {
            "messages": [updated_message],
            "suggestions": suggestions_data,
        }

    def _parse_suggestions(
        self, content: str
    ) -> tuple[str, SuggestionsData | None]:
        """从消息内容中解析建议选项.

        Args:
            content: 原始消息内容

        Returns:
            tuple of (清理后的内容, 建议数据或 None)
        """
        suggestions_data = None
        cleaned_content = content

        # 尝试 JSON 代码块格式: ```suggestions { ... } ```
        json_pattern = r"```suggestions\s*(\{[\s\S]*?\})\s*```"
        match = re.search(json_pattern, content, re.IGNORECASE)
        if match:
            try:
                raw_data = json.loads(match.group(1))
                suggestions_data = self._normalize_suggestions(raw_data)
                cleaned_content = re.sub(
                    json_pattern, "", content, flags=re.IGNORECASE
                ).strip()
            except json.JSONDecodeError:
                pass

        # 尝试 XML 标签格式: <suggestions>...</suggestions>
        if not suggestions_data:
            xml_pattern = r"<suggestions>([\s\S]*?)</suggestions>"
            match = re.search(xml_pattern, content, re.IGNORECASE)
            if match:
                try:
                    raw_data = json.loads(match.group(1))
                    suggestions_data = self._normalize_suggestions(raw_data)
                    cleaned_content = re.sub(
                        xml_pattern, "", content, flags=re.IGNORECASE
                    ).strip()
                except json.JSONDecodeError:
                    # 尝试按行解析（每行一个建议）
                    lines = [
                        line.strip()
                        for line in match.group(1).strip().split("\n")
                        if line.strip()
                    ]
                    if lines:
                        suggestions_data = SuggestionsData(
                            suggestions=[
                                Suggestion(id=str(i + 1), text=line)
                                for i, line in enumerate(lines)
                            ],
                            multi_select=False,
                        )
                        cleaned_content = re.sub(
                            xml_pattern, "", content, flags=re.IGNORECASE
                        ).strip()

        return cleaned_content, suggestions_data

    def _normalize_suggestions(
        self, raw_data: dict[str, Any]
    ) -> SuggestionsData:
        """规范化建议数据，确保每个建议都有 id."""
        suggestions = raw_data.get("suggestions", [])
        normalized = []
        for i, s in enumerate(suggestions):
            if isinstance(s, dict):
                normalized.append(
                    Suggestion(
                        id=s.get("id", str(i + 1)),
                        text=s.get("text", ""),
                        value=s.get("value"),
                    )
                )
            elif isinstance(s, str):
                normalized.append(Suggestion(id=str(i + 1), text=s))

        return SuggestionsData(
            suggestions=normalized,
            multi_select=raw_data.get("multi_select", False),
            prompt=raw_data.get("prompt"),
        )
