"""SpeechTemplate Middleware - 话术模板工具和状态管理.

提供 `add_speech_template` tool，供 LLM 调用以添加话术模板（建议选项）。
话术模板会存储到 state 中，并通过 SSE 推送到前端。

Prompt 中的使用格式：
1. 带提示语：添加话术: -请问需要进行仿真吗？-> 建议选项：进行仿真,结束任务
2. 直接选项：添加话术: 进行仿真,结束任务
"""

from __future__ import annotations

import logging

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools import tool, ToolRuntime
from langgraph.types import Command
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------

class SpeechOption(BaseModel):
    """单个话术选项."""

    id: str = Field(description="选项唯一标识")
    text: str = Field(description="选项显示文本")
    value: str | None = Field(default=None, description="选项值（可选，默认为 text）")


class SpeechTemplateData(BaseModel):
    """话术模板数据结构."""

    prompt: str | None = Field(default=None, description="提示语（可选）")
    options: list[SpeechOption] = Field(description="话术选项列表")
    multi_select: bool = Field(default=False, description="是否支持多选")


# ---------------------------------------------------------------------------
# add_speech_template Tool
# ---------------------------------------------------------------------------

@tool
def add_speech_template(
    options: list[str],
    runtime: ToolRuntime,
    prompt: str | None = None,
    multi_select: bool = False,
) -> Command:
    """添加话术模板，为用户提供快捷回复选项.

    当需要引导用户进行下一步操作时使用此工具。话术模板会在前端显示为
    可点击的建议选项，帮助用户快速响应。

    **Prompt 中的格式**（供参考）：
    - `添加话术`: 请问需要进行仿真吗？-> 建议选项：进行仿真,结束任务
    - `添加话术`: 进行仿真,结束任务

    Args:
        options: 话术选项列表，如 ["进行仿真", "结束任务"]
        runtime: ToolRuntime，由 LangChain 自动注入
        prompt: 可选提示语，如 "请问需要进行仿真吗？"
        multi_select: 是否允许多选，默认为单选

    Returns:
        Command 包含状态更新
    """
    if not options:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="话术选项不能为空",
                        tool_call_id=runtime.tool_call_id,
                        status="error",
                    )
                ]
            }
        )

    # 构建话术选项
    speech_options = [
        SpeechOption(id=str(i + 1), text=opt, value=opt)
        for i, opt in enumerate(options)
    ]

    # 构建话术模板数据
    template_data = SpeechTemplateData(
        prompt=prompt,
        options=speech_options,
        multi_select=multi_select,
    )

    logger.info(
        f"SpeechTemplateMiddleware: 添加话术模板 "
        f"prompt='{prompt}' options={options} multi_select={multi_select}"
    )

    # 返回 Command 更新状态
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"已添加话术模板：{', '.join(options)}",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
            "suggestions": template_data,
        }
    )


# ---------------------------------------------------------------------------
# SpeechTemplateMiddleware
# ---------------------------------------------------------------------------

class SuggestionsMiddleware(AgentMiddleware):
    """话术模板 Middleware.

    功能：
    1. 注册 add_speech_template tool 供 LLM 调用
    2. 话术通过 tool 调用存储到 state.suggestions 中

    注意：state_schema 由 core.py 中的 WINSAgentState 统一定义。
    """

    name: str = "suggestions"

    # 注册 tools 为类变量
    tools = [add_speech_template]
