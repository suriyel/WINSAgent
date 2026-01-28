"""Tool Registry: central management of all available tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from app.agent.middleware.missing_params import ParamSchema


class ToolRegistry:
    """Central registry for all Agent tools.

    Stores tools alongside category, HITL, and param edit metadata so the Agent
    and API layer can introspect the available capabilities.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = {}
        self._hitl_required: set[str] = set()
        self._param_edit_schemas: dict[str, dict[str, "ParamSchema"]] = {}

    # ---- registration ----

    def register(
        self,
        tool: BaseTool,
        *,
        category: str = "query",
        requires_hitl: bool = False,
        param_edit_schema: dict[str, "ParamSchema"] | None = None,
    ) -> None:
        """Register a tool with optional metadata.

        Args:
            tool: The LangChain tool to register.
            category: Tool category ("query" or "mutation").
            requires_hitl: Whether tool requires human-in-the-loop approval.
            param_edit_schema: Optional schema for missing params editing.
                Maps parameter names to ParamSchema definitions.
                If provided, the MissingParamsMiddleware will use this
                to generate UI forms for missing parameters.
        """
        name = tool.name
        self._tools[name] = tool
        self._categories.setdefault(category, []).append(name)
        if requires_hitl:
            self._hitl_required.add(name)
        if param_edit_schema:
            self._param_edit_schemas[name] = param_edit_schema

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

    def get_param_edit_config(self) -> dict[str, dict[str, "ParamSchema"]]:
        """Return tools_with_param_edit config for MissingParamsMiddleware."""
        return self._param_edit_schemas.copy()

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return serialisable definitions for the GET /api/tools endpoint."""
        defs: list[dict[str, Any]] = []
        # Build reverse category lookup
        name_to_cat: dict[str, str] = {}
        for cat, names in self._categories.items():
            for n in names:
                name_to_cat[n] = cat
        for name, tool in self._tools.items():
            tool_def: dict[str, Any] = {
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
            # Include param edit schema if defined
            if name in self._param_edit_schemas:
                tool_def["param_edit_schema"] = {
                    k: v.model_dump(exclude_none=True)
                    for k, v in self._param_edit_schemas[name].items()
                }
            defs.append(tool_def)
        return defs


# Singleton
tool_registry = ToolRegistry()
