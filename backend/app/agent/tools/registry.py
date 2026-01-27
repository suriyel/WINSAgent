"""Tool Registry: central management of all available tools."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool


class ToolRegistry:
    """Central registry for all Agent tools.

    Stores tools alongside category and HITL metadata so the Agent
    and API layer can introspect the available capabilities.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = {}
        self._hitl_required: set[str] = set()

    # ---- registration ----

    def register(
        self,
        tool: BaseTool,
        *,
        category: str = "query",
        requires_hitl: bool = False,
    ) -> None:
        name = tool.name
        self._tools[name] = tool
        self._categories.setdefault(category, []).append(name)
        if requires_hitl:
            self._hitl_required.add(name)

    # ---- queries ----

    def get_all_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_tool(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_tools_by_category(self, category: str) -> list[BaseTool]:
        names = self._categories.get(category, [])
        return [self._tools[n] for n in names if n in self._tools]

    def get_hitl_config(self) -> dict[str, bool]:
        """Return interrupt_on config for HumanInTheLoopMiddleware."""
        return {name: True for name in self._hitl_required}

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return serialisable definitions for the GET /api/tools endpoint."""
        defs: list[dict[str, Any]] = []
        # Build reverse category lookup
        name_to_cat: dict[str, str] = {}
        for cat, names in self._categories.items():
            for n in names:
                name_to_cat[n] = cat
        for name, tool in self._tools.items():
            defs.append(
                {
                    "name": name,
                    "description": tool.description,
                    "parameters_schema": (
                        tool.args_schema.model_json_schema()
                        if tool.args_schema
                        else {}
                    ),
                    "category": name_to_cat.get(name, "query"),
                    "requires_hitl": name in self._hitl_required,
                }
            )
        return defs


# Singleton
tool_registry = ToolRegistry()
