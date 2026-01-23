"""
Tools API 端点
提供工具列表、详情、Schema 查询
"""

from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.tools.base import ToolRegistry, get_default_tools


router = APIRouter()


class ToolInfo(BaseModel):
    """工具信息"""
    name: str = Field(description="工具名称")
    description: str = Field(description="工具描述")
    requires_approval: bool = Field(default=False, description="是否需要审批")


class ToolSchema(BaseModel):
    """工具参数 Schema"""
    name: str = Field(description="工具名称")
    description: str = Field(description="工具描述")
    parameters: dict[str, Any] = Field(description="参数定义")
    required: list[str] = Field(default_factory=list, description="必填参数列表")


class ToolListResponse(BaseModel):
    """工具列表响应"""
    tools: list[ToolInfo]
    total: int


@router.get("/", response_model=ToolListResponse)
async def list_tools():
    """获取所有可用工具列表"""
    # 确保工具已注册
    get_default_tools()

    tools = ToolRegistry.get_all()
    tool_list = []

    for tool in tools:
        tool_list.append(ToolInfo(
            name=tool.name,
            description=tool.description or "",
            requires_approval=getattr(tool, "requires_approval", False),
        ))

    return ToolListResponse(tools=tool_list, total=len(tool_list))


@router.get("/{name}", response_model=ToolInfo)
async def get_tool(name: str):
    """获取指定工具详情"""
    # 确保工具已注册
    get_default_tools()

    tool = ToolRegistry.get(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 不存在")

    return ToolInfo(
        name=tool.name,
        description=tool.description or "",
        requires_approval=getattr(tool, "requires_approval", False),
    )


@router.get("/{name}/schema", response_model=ToolSchema)
async def get_tool_schema(name: str):
    """获取工具参数 Schema"""
    # 确保工具已注册
    get_default_tools()

    tool = ToolRegistry.get(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 不存在")

    # 提取参数 Schema
    parameters = {}
    required = []

    if tool.args_schema:
        for field_name, field_info in tool.args_schema.model_fields.items():
            # 获取字段类型
            field_type = "string"
            annotation = field_info.annotation

            if annotation == int:
                field_type = "integer"
            elif annotation == float:
                field_type = "number"
            elif annotation == bool:
                field_type = "boolean"
            elif hasattr(annotation, "__origin__"):
                if annotation.__origin__ is list:
                    field_type = "array"
                elif annotation.__origin__ is dict:
                    field_type = "object"

            parameters[field_name] = {
                "type": field_type,
                "description": field_info.description or "",
            }

            # 添加默认值
            if field_info.default is not None:
                parameters[field_name]["default"] = field_info.default

            # 记录必填字段
            if field_info.is_required():
                required.append(field_name)

    return ToolSchema(
        name=tool.name,
        description=tool.description or "",
        parameters=parameters,
        required=required,
    )
