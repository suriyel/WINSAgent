"""Agent core: builds the main Agent with middleware and tools."""

from __future__ import annotations

import logging

from langchain.agents.middleware import ContextEditingMiddleware, ClearToolUsesEdit
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.middleware.chart_data import ChartDataMiddleware
from app.agent.middleware.data_table import DataTableMiddleware
from app.agent.middleware.missing_params import MissingParamsMiddleware
from app.agent.middleware.suggestions import SuggestionsMiddleware
from app.agent.subagents import SubAgentMiddleware
from app.agent.subagents.agents.todo_tracker import TODO_TRACKER_CONFIG
from app.agent.tools.telecom_tools import register_telecom_tools
from app.agent.tools.hil import CustomHumanInTheLoopMiddleware
from app.agent.tools.knowledge import register_knowledge_tools
from app.agent.tools.registry import tool_registry
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是 WINS Agent 工作台的智能助手，专注于通信网络优化仿真场景。你的核心职责是：

1. **理解用户意图**：准确识别用户关注的网络问题类型（弱覆盖、干扰、容量、切换等），确定需要查询的指标。
2. **领域知识检索**：**必须**在执行任何分析前，先调用 search_terminology 工具查询相关术语和指标定义，再调用 search_design_doc 工具获取对应的分析流程。这两个工具的优先级最高。
3. **工具编排**：按照正确的流程顺序调用工具：
   - 第一步：调用 search_terminology 和 search_design_doc 获取领域知识
   - 第二步：调用 match_scenario 匹配场景获取 digitaltwinsId
   - 第三步：调用 query_root_cause_analysis 查询根因分析结果
   - 第四步：**必须**输出固定提示语（见下方规则）
   - 第五步：如用户确认需要优化，调用 query_simulation_results 查询仿真结果
4. **指标选择**：根据用户意图和检索到的术语定义，**只查询相关指标**，不要查询全部指标。例如：
   - 用户问"弱覆盖" → 查询 RSRP、MR覆盖率、覆盖电平等相关指标
   - 用户问"干扰" → 查询 SINR、RSRQ、重叠覆盖度等相关指标
   - 用户问"容量" → 查询 PRB利用率、下行流量、用户数等相关指标

## 根因分析后的固定提示（必须遵守）

在展示根因分析结果后，你**必须**输出以下固定提示语（一字不差）：

**"根因分析完成。是否需要对该场景进行优化仿真？"**

这条提示语不可省略、不可修改、不可替换。

## 分析粒度

每次分析需要考虑两种粒度：
- **小区级(cell)**：以基站小区为最小分析单元，包含小区id、经纬度和小区级指标
- **栅格级(grid)**：以地理栅格为最小分析单元，包含经纬度和栅格级指标

根据 search_design_doc 返回的流程文档，确定应该执行小区级分析、栅格级分析，还是两者都执行。

## 缺省参数处理

当你准备调用工具但发现某些必填参数无法通过上下文或查询工具获得时：
   - **务必**先尝试使用查询工具获取参数值
   - 仍无法确定的参数，**只能**让用户提供，**必须**使用以下格式：
```params_request
{
  "tool_name": "工具名称",
  "known_params": {"已确定的参数名": "值"},
  "missing_params": ["缺失参数1", "缺失参数2"]
}
```
   - **数组类型参数**的值必须使用 JSON 数组格式，如 `["RSRP均值(dBm)", "MR覆盖率(%)"]`
   - **绝对不要**通过对话文本向用户询问参数值，必须使用上述格式

## 注意事项

- 工具调用失败时，整个任务终止，不要重试
- 始终用中文回复用户
- 展示分析结果时，简要总结关键发现

## 建议回复选项

在每次回复结束时，你应该提供 2-4 个建议的快捷回复选项，帮助用户快速选择下一步操作。使用以下格式：

**单选模式**（用户只能选择一个）:
```suggestions
{
  "suggestions": [
    {"text": "选项1文本"},
    {"text": "选项2文本"},
    {"text": "选项3文本"}
  ]
}
```

**多选模式**（用户可以选择多个）:
```suggestions
{
  "suggestions": [
    {"text": "选项1"},
    {"text": "选项2"},
    {"text": "选项3"}
  ],
  "multi_select": true,
  "prompt": "请选择需要查询的项目（可多选）"
}
```

建议选项应该：
- 与当前对话上下文相关
- 预测用户可能的下一步操作
- 使用简洁明确的文字
- 在根因分析后，提供"是，进行优化仿真"和"否，暂不优化"选项
"""

# In-memory checkpointer for dev/validation stage
_checkpointer = InMemorySaver()

# Track whether tools have been registered
_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    register_telecom_tools()
    register_knowledge_tools()
    _initialized = True


def build_agent():
    """Build and return the main Agent (CompiledStateGraph)."""
    _ensure_initialized()

    all_tools = tool_registry.get_all_tools()
    hitl_config = tool_registry.get_hitl_config()
    param_edit_config = tool_registry.get_param_edit_config()

    # SubAgent Middleware（替代 TodoListMiddleware）
    subagent_mw = SubAgentMiddleware(
        delegated=[],
        reactive=[TODO_TRACKER_CONFIG],
    )
    # 注入 task() tool（如有委派式子 Agent）
    all_tools.extend(subagent_mw.tools)

    middleware = [
        subagent_mw,
        DataTableMiddleware(),
        ChartDataMiddleware(),
        SuggestionsMiddleware(),
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger= 3000,
                    keep=2,
                    clear_tool_inputs= True,
                    exclude_tools=[
                        'search_design_doc',
                        'search_terminology',
                    ],
                    placeholder="[cleared]"
                ),
            ]
        )
    ]

    # Add MissingParams middleware when there are tools with param edit schema
    if param_edit_config:
        middleware.append(
            MissingParamsMiddleware(
                tools_with_param_edit=param_edit_config,
                description_prefix="请填写以下参数",
            )
        )

    # Only add HITL middleware when there are tools requiring it
    if hitl_config:
        middleware.append(
            CustomHumanInTheLoopMiddleware(
                interrupt_on=hitl_config,
                description_prefix="该操作需要您确认",
            )
        )

    # 1. 配置通义千问的 OpenAI 兼容实例
    llm = ChatOpenAI(
        model=settings.llm_model,  # 例如 "qwen-max"
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        streaming=True
    )

    agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=middleware,
        checkpointer=_checkpointer,
    )
    return agent


# Lazily-created singleton
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def get_checkpointer() -> InMemorySaver:
    return _checkpointer
