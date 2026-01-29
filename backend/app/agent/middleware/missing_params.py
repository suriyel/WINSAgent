"""Missing Parameters Middleware - 检测工具缺省参数并触发 interrupt 让用户填写.

参考 Airflow 的 Params 模式，提供 JSON Schema 兼容的参数定义，
支持在前端生成动态表单供用户编辑缺省参数。
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Param Schema 模型 - 参照 Airflow Params + JSON Schema
# ---------------------------------------------------------------------------


class ParamSchema(BaseModel):
    """单个参数的 Schema 定义，兼容 JSON Schema 规范.

    参考 Airflow 的 Params 设计:
    https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/params.html
    """

    # 基础信息
    type: str | list[str] = Field(
        default="string",
        description="参数类型: string, number, integer, boolean, array, object, null 或组合",
    )
    title: str | None = Field(default=None, description="表单字段标签")
    description: str | None = Field(default=None, description="帮助文本/提示")

    # 默认值
    default: Any = Field(default=None, description="默认值")

    # 约束 - 字符串
    minLength: int | None = Field(default=None, description="字符串最小长度")
    maxLength: int | None = Field(default=None, description="字符串最大长度")
    pattern: str | None = Field(default=None, description="正则表达式验证")
    format: str | None = Field(
        default=None,
        description="特殊格式: date, date-time, time, email, uri, multiline",
    )

    # 约束 - 数值
    minimum: float | None = Field(default=None, description="数值最小值")
    maximum: float | None = Field(default=None, description="数值最大值")
    exclusiveMinimum: float | None = Field(default=None, description="数值排他最小值")
    exclusiveMaximum: float | None = Field(default=None, description="数值排他最大值")
    multipleOf: float | None = Field(default=None, description="数值步进")

    # 约束 - 枚举/选项
    enum: list[Any] | None = Field(default=None, description="可选值列表（下拉选择）")
    examples: list[Any] | None = Field(
        default=None,
        description="建议值列表（可输入也可选择）",
    )
    values_display: dict[str, str] | None = Field(
        default=None,
        description="enum/examples 的显示标签映射",
    )

    # 约束 - 数组
    items: dict[str, Any] | None = Field(
        default=None,
        description="数组元素的 schema 定义",
    )
    minItems: int | None = Field(default=None, description="数组最小长度")
    maxItems: int | None = Field(default=None, description="数组最大长度")
    uniqueItems: bool | None = Field(default=None, description="数组元素是否唯一")

    # UI 相关
    section: str | None = Field(default=None, description="表单分组名称")
    const: Any | None = Field(default=None, description="隐藏字段的固定值")

    # 扩展元数据
    placeholder: str | None = Field(default=None, description="输入框占位提示")

    def is_required(self) -> bool:
        """判断参数是否必填.

        按照 Airflow 规范：有类型的字段默认必填。
        要使字段可选，需要允许 null 类型，如 type=["null", "string"]
        """
        if isinstance(self.type, list):
            return "null" not in self.type
        return self.type != "null"


class MissingParamsInfo(BaseModel):
    """缺省参数信息，用于 interrupt 传递给前端."""

    tool_name: str = Field(description="工具名称")
    tool_call_id: str = Field(description="工具调用 ID")
    description: str | None = Field(default=None, description="工具描述")
    current_params: dict[str, Any] = Field(
        default_factory=dict,
        description="当前已提供的参数值",
    )
    missing_params: list[str] = Field(
        default_factory=list,
        description="缺失的必填参数名列表",
    )
    params_schema: dict[str, ParamSchema] = Field(
        default_factory=dict,
        description="所有可编辑参数的 schema 定义",
    )


class MissingParamsState(AgentState):
    """扩展的 Agent State，包含 missing_params 字段."""

    missing_params_pending: MissingParamsInfo | None


# ---------------------------------------------------------------------------
# Middleware 实现
# ---------------------------------------------------------------------------


class MissingParamsMiddleware(AgentMiddleware[MissingParamsState]):
    """检测工具调用中的缺省参数并触发 interrupt.

    当工具被调用但存在缺省/空值参数时，此 middleware 会：
    1. 根据工具的 args_schema 检测缺失的必填参数
    2. 触发 interrupt 并传递参数 schema 给前端
    3. 前端渲染表单让用户填写
    4. 用户提交后恢复执行

    与 HumanInTheLoopMiddleware 不同，此 middleware：
    - 不是为了获取授权确认
    - 而是为了让用户补充缺失的参数值
    """

    name: str = "missing_params"
    state_schema = MissingParamsState

    def __init__(
        self,
        *,
        tools_with_param_edit: dict[str, dict[str, ParamSchema]] | None = None,
        check_all_tools: bool = False,
        description_prefix: str = "请填写以下参数",
    ):
        """初始化 MissingParamsMiddleware.

        Args:
            tools_with_param_edit: 工具名到参数 schema 的映射。
                如果指定，只对这些工具检测缺省参数。
            check_all_tools: 是否检查所有工具的缺省参数。
                如果为 True，会自动从工具的 args_schema 推断参数定义。
            description_prefix: 中断描述前缀。
        """
        self._tools_schema = tools_with_param_edit or {}
        self._check_all = check_all_tools
        self._description_prefix = description_prefix

    def before_tool(
        self,
        state: MissingParamsState,
        tool_call: dict[str, Any],
    ) -> dict[str, Any] | None:
        """在工具执行前检查缺省参数."""
        tool_name = tool_call.get("name", "")
        tool_call_id = tool_call.get("id", "")
        tool_args = tool_call.get("args", {})

        # 获取参数 schema
        params_schema = self._get_params_schema(tool_name, state)
        if not params_schema:
            return None

        # 检测缺失的必填参数
        missing = []
        for param_name, schema in params_schema.items():
            if not schema.is_required():
                continue
            value = tool_args.get(param_name)
            if self._is_empty_value(value):
                missing.append(param_name)

        if not missing:
            return None

        # 构建缺省参数信息
        info = MissingParamsInfo(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            description=f"{self._description_prefix}: {tool_name}",
            current_params=tool_args,
            missing_params=missing,
            params_schema=params_schema,
        )

        logger.info(
            f"MissingParamsMiddleware: 检测到工具 {tool_name} 缺少参数 {missing}，触发 interrupt"
        )

        # 触发 interrupt
        result = interrupt(
            {
                "type": "params_edit",
                "info": info.model_dump(),
            }
        )

        # 处理用户响应
        action = result.get("action", "cancel")
        if action == "submit":
            # 用户提交了参数，更新 tool_args
            edited_params = result.get("params", {})
            merged_args = {**tool_args, **edited_params}
            # 返回更新后的 tool_call
            return {
                "tool_call": {
                    **tool_call,
                    "args": merged_args,
                }
            }
        elif action == "cancel":
            # 用户取消，可以选择跳过工具执行或抛出异常
            logger.info(f"MissingParamsMiddleware: 用户取消了参数编辑")
            # 返回一个特殊标记，让工具不执行
            from langchain_core.messages import ToolMessage
            return {
                "messages": [
                    ToolMessage(
                        content="用户取消了参数编辑，操作已终止。",
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        status="error",
                    )
                ],
                "skip_tool": True,
            }

        return None

    def _get_params_schema(
        self,
        tool_name: str,
        state: MissingParamsState,
    ) -> dict[str, ParamSchema] | None:
        """获取工具的参数 schema.

        优先使用配置的 schema，否则尝试从工具的 args_schema 推断。
        """
        # 优先使用配置
        if tool_name in self._tools_schema:
            return self._tools_schema[tool_name]

        if not self._check_all:
            return None

        # 从 state 中的 tools 推断（如果有的话）
        # 这需要 agent 在构建时传入工具列表
        tools = getattr(state, "_tools", None)
        if not tools:
            return None

        for tool in tools:
            if tool.name == tool_name and tool.args_schema:
                return self._infer_schema_from_pydantic(tool.args_schema)

        return None

    def _infer_schema_from_pydantic(
        self,
        schema_class: type,
    ) -> dict[str, ParamSchema]:
        """从 Pydantic 模型推断参数 schema."""
        try:
            json_schema = schema_class.model_json_schema()
            properties = json_schema.get("properties", {})
            required = set(json_schema.get("required", []))

            result = {}
            for name, prop in properties.items():
                param_type = prop.get("type", "string")
                # 如果不在 required 中，添加 null 类型
                if name not in required:
                    if isinstance(param_type, list):
                        if "null" not in param_type:
                            param_type = param_type + ["null"]
                    else:
                        param_type = [param_type, "null"]

                result[name] = ParamSchema(
                    type=param_type,
                    title=prop.get("title", name),
                    description=prop.get("description"),
                    default=prop.get("default"),
                    enum=prop.get("enum"),
                    minimum=prop.get("minimum"),
                    maximum=prop.get("maximum"),
                    minLength=prop.get("minLength"),
                    maxLength=prop.get("maxLength"),
                    pattern=prop.get("pattern"),
                    format=prop.get("format"),
                )

            return result
        except Exception as e:
            logger.warning(f"无法从 Pydantic 模型推断 schema: {e}")
            return {}

    def _is_empty_value(self, value: Any) -> bool:
        """判断值是否为空/缺省."""
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, (list, dict)) and len(value) == 0:
            return True
        return False


# ---------------------------------------------------------------------------
# 辅助函数 - 创建常用的 ParamSchema
# ---------------------------------------------------------------------------


def param_edit(schema: dict[str, ParamSchema]):
    """Decorator: attach param_edit_schema directly on a @tool instance.

    Usage::

        @param_edit({
            "customer_id": string_param(title="客户编码"),
            "address": string_param(title="配送地址"),
        })
        @tool
        def create_order(customer_id: str, address: str) -> str:
            ...

    Note: ``@param_edit`` must be placed **above** ``@tool`` so that it
    receives the already-constructed ``BaseTool`` object.  The registry
    will auto-detect the ``_param_edit_schema`` attribute during
    ``register()`` — no need to pass ``param_edit_schema=`` explicitly.
    """

    def decorator(tool_obj):
        tool_obj._param_edit_schema = schema
        return tool_obj

    return decorator


def string_param(
    title: str | None = None,
    description: str | None = None,
    default: str | None = None,
    *,
    required: bool = True,
    enum: list[str] | None = None,
    format: str | None = None,
    placeholder: str | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
) -> ParamSchema:
    """创建字符串类型参数 schema."""
    return ParamSchema(
        type="string" if required else ["string", "null"],
        title=title,
        description=description,
        default=default,
        enum=enum,
        format=format,
        placeholder=placeholder,
        minLength=min_length,
        maxLength=max_length,
    )


def number_param(
    title: str | None = None,
    description: str | None = None,
    default: float | None = None,
    *,
    required: bool = True,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
) -> ParamSchema:
    """创建数值类型参数 schema."""
    return ParamSchema(
        type="number" if required else ["number", "null"],
        title=title,
        description=description,
        default=default,
        minimum=minimum,
        maximum=maximum,
        multipleOf=step,
    )


def integer_param(
    title: str | None = None,
    description: str | None = None,
    default: int | None = None,
    *,
    required: bool = True,
    minimum: int | None = None,
    maximum: int | None = None,
) -> ParamSchema:
    """创建整数类型参数 schema."""
    return ParamSchema(
        type="integer" if required else ["integer", "null"],
        title=title,
        description=description,
        default=default,
        minimum=minimum,
        maximum=maximum,
    )


def boolean_param(
    title: str | None = None,
    description: str | None = None,
    default: bool | None = None,
    *,
    required: bool = True,
) -> ParamSchema:
    """创建布尔类型参数 schema."""
    return ParamSchema(
        type="boolean" if required else ["boolean", "null"],
        title=title,
        description=description,
        default=default,
    )


def select_param(
    options: list[str],
    title: str | None = None,
    description: str | None = None,
    default: str | None = None,
    *,
    required: bool = True,
    display_labels: dict[str, str] | None = None,
) -> ParamSchema:
    """创建下拉选择参数 schema."""
    return ParamSchema(
        type="string" if required else ["string", "null"],
        title=title,
        description=description,
        default=default,
        enum=options,
        values_display=display_labels,
    )


def date_param(
    title: str | None = None,
    description: str | None = None,
    default: str | None = None,
    *,
    required: bool = True,
) -> ParamSchema:
    """创建日期类型参数 schema."""
    return ParamSchema(
        type="string" if required else ["string", "null"],
        title=title,
        description=description,
        default=default,
        format="date",
    )


def datetime_param(
    title: str | None = None,
    description: str | None = None,
    default: str | None = None,
    *,
    required: bool = True,
) -> ParamSchema:
    """创建日期时间类型参数 schema."""
    return ParamSchema(
        type="string" if required else ["string", "null"],
        title=title,
        description=description,
        default=default,
        format="date-time",
    )


def array_param(
    item_type: str = "string",
    title: str | None = None,
    description: str | None = None,
    default: list | None = None,
    *,
    required: bool = True,
    min_items: int | None = None,
    max_items: int | None = None,
    placeholder: str | None = None,
) -> ParamSchema:
    """创建数组类型参数 schema."""
    return ParamSchema(
        type="array" if required else ["array", "null"],
        title=title,
        description=description,
        default=default,
        items={"type": item_type},
        minItems=min_items,
        maxItems=max_items,
        placeholder=placeholder,
    )


def multiline_param(
    title: str | None = None,
    description: str | None = None,
    default: str | None = None,
    *,
    required: bool = True,
    placeholder: str | None = None,
) -> ParamSchema:
    """创建多行文本参数 schema."""
    return ParamSchema(
        type="string" if required else ["string", "null"],
        title=title,
        description=description,
        default=default,
        format="multiline",
        placeholder=placeholder,
    )
