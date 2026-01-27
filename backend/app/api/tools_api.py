"""GET /api/tools — List registered tools."""

from __future__ import annotations

from fastapi import APIRouter

from app.agent.tools.registry import tool_registry

router = APIRouter()


@router.get("/tools")
async def list_tools():
    """Return all registered tool definitions."""
    # Ensure tools are registered
    from app.agent.core import _ensure_initialized

    _ensure_initialized()
    return tool_registry.get_tool_definitions()
