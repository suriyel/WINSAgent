"""DataTableMiddleware - 截断大表数据，减少 LLM 上下文，全量数据通过 SSE 发送前端.

对工具返回的 [DATA_TABLE]...[/DATA_TABLE] 块：
- 截断 ToolMessage.content 至 top N 行（供 LLM 使用）
- 完整结构化数据存入 ToolMessage.additional_kwargs["table_data"]
- event_mapper 检测后发射独立的 table.data SSE 事件
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.typing import ContextT
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 保留在 LLM 上下文中的最大数据行数（不含表头）
TABLE_ROWS_FOR_LLM = 5

TABLE_TAG_START = "[DATA_TABLE]"
TABLE_TAG_END = "[/DATA_TABLE]"

_TABLE_PATTERN = re.compile(
    rf"{re.escape(TABLE_TAG_START)}(.*?){re.escape(TABLE_TAG_END)}",
    re.DOTALL,
)


class TableData(BaseModel):
    """从工具结果中提取的结构化表格数据."""

    headers: list[str]
    rows: list[list[str]]
    total_rows: int
    truncated: bool


class DataTableMiddleware(AgentMiddleware[AgentState, ContextT]):
    """拦截工具结果中的 [DATA_TABLE] 块，截断上下文并提取全量数据.

    使用 wrap_tool_call 钩子，对任何返回 [DATA_TABLE] 标记的工具透明生效。
    """

    name: str = "data_table"

    def wrap_tool_call(
        self,
        request: dict[str, Any],
        handler: Any,
    ) -> ToolMessage:
        result = handler(request)

        if not isinstance(result, ToolMessage):
            return result

        content = result.content
        if not isinstance(content, str) or TABLE_TAG_START not in content:
            return result

        tables, truncated_content = self._process_tables(content)

        if not tables:
            return result

        logger.info(
            "DataTableMiddleware: processed %d table(s), "
            "truncated LLM context to %d rows each",
            len(tables),
            TABLE_ROWS_FOR_LLM,
        )

        return ToolMessage(
            content=truncated_content,
            tool_call_id=result.tool_call_id,
            name=result.name,
            status=getattr(result, "status", "success"),
            additional_kwargs={
                **result.additional_kwargs,
                "table_data": [t.model_dump() for t in tables],
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_tables(
        self, content: str
    ) -> tuple[list[TableData], str]:
        """提取所有 [DATA_TABLE] 块，返回 (结构化数据列表, 截断后的内容)."""
        tables: list[TableData] = []
        truncated_content = content

        for match in _TABLE_PATTERN.finditer(content):
            csv_text = match.group(1).strip()
            table = self._parse_csv(csv_text)

            if table is None:
                continue

            tables.append(table)

            truncated_csv = self._truncate_csv(csv_text, TABLE_ROWS_FOR_LLM)
            truncated_content = truncated_content.replace(
                match.group(0),
                f"{TABLE_TAG_START}\n{truncated_csv}\n{TABLE_TAG_END}",
                1,
            )

        return tables, truncated_content

    @staticmethod
    def _parse_csv(csv_text: str) -> TableData | None:
        """将 CSV 文本解析为 TableData."""
        lines = [line for line in csv_text.split("\n") if line.strip()]
        if not lines:
            return None

        headers = [h.strip() for h in lines[0].split(",")]
        rows = [[c.strip() for c in line.split(",")] for line in lines[1:]]

        return TableData(
            headers=headers,
            rows=rows,
            total_rows=len(rows),
            truncated=len(rows) > TABLE_ROWS_FOR_LLM,
        )

    @staticmethod
    def _truncate_csv(csv_text: str, max_rows: int) -> str:
        """截断 CSV 至 max_rows 行数据（不含表头），超出部分加摘要."""
        lines = [line for line in csv_text.split("\n") if line.strip()]
        total_data_rows = len(lines) - 1  # 减去表头

        if total_data_rows <= max_rows:
            return csv_text

        kept = lines[: max_rows + 1]  # header + max_rows
        kept.append(f"... 共 {total_data_rows} 条记录，仅展示前 {max_rows} 条")
        return "\n".join(kept)
