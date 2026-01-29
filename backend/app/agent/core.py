"""Agent core: builds the main Agent with middleware and tools."""

from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware.human_in_the_loop import HumanInTheLoopMiddleware
from langchain.agents.middleware.todo import TodoListMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.middleware.missing_params import MissingParamsMiddleware
from app.agent.middleware.suggestions import SuggestionsMiddleware
from app.agent.tools.demo_tools import register_demo_tools
from app.agent.tools.hil import CustomHumanInTheLoopMiddleware
from app.agent.tools.knowledge import register_knowledge_tools
from app.agent.subagents.data_analysis import register_subagent_tools
from app.agent.tools.registry import tool_registry
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是 WINS Agent 工作台的智能助手。你的核心职责是：

1. **理解用户意图**：准确识别用户需求，选取合适的工具完成任务。
2. **领域知识检索**：当遇到专业术语或需要系统设计信息时，主动调用 search_terminology 或 search_design_doc 工具获取上下文。
3. **工具编排**：根据工具的依赖关系，按正确顺序调用工具。例如创建订单前需先验证客户。
4. **参数填充**：结合领域知识和上下文，准确填写工具参数。
5. **任务规划**：使用 write_todos 工具记录任务步骤计划，便于用户跟踪进度。

6. **缺省参数处理**：当你准备调用工具但发现某些必填参数无法通过上下文或查询工具获得时：
   - 务必先尝试使用查询工具（如 search_customer、check_inventory）获取参数值
   - 查询后仍无法确定的参数，**必须**使用以下格式输出参数请求，系统会自动弹出表单让用户填写：
```params_request
{
  "tool_name": "工具名称",
  "known_params": {"已确定的参数名": "值"},
  "missing_params": ["缺失参数1", "缺失参数2"]
}
```
   - **known_params 必须包含所有已知值**：不仅包含用户直接提供的参数，还必须包含之前工具调用结果中获得的相关值。例如：如果之前 check_inventory 查询了产品 P001，则 known_params 中应包含 `"product_codes": ["P001"]`；如果 search_customer 返回了客户编码 C001，则应包含 `"customer_id": "C001"`。
   - **数组类型参数**的值必须使用 JSON 数组格式，如 `["P001", "P002"]`、`[10, 20]`
   - **绝对不要**通过对话文本向用户询问参数值，必须使用上述格式

注意事项：
- 工具调用失败时，整个任务终止，不要重试
- 需要HITL确认的操作会暂停等待用户批准
- 始终用中文回复用户

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

**多选模式**（用户可以选择多个，如同时查询多个客户）:
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
- 包含常见的后续操作如"继续"、"查看详情"、"取消"等
"""

# In-memory checkpointer for dev/validation stage
_checkpointer = InMemorySaver()

# Track whether tools have been registered
_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    register_demo_tools()
    register_knowledge_tools()
    register_subagent_tools()
    _initialized = True


def build_agent():
    """Build and return the main Agent (CompiledStateGraph)."""
    _ensure_initialized()

    all_tools = tool_registry.get_all_tools()
    hitl_config = tool_registry.get_hitl_config()
    param_edit_config = tool_registry.get_param_edit_config()

    middleware = [
        TodoListMiddleware(),
        SuggestionsMiddleware(),
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
        openai_api_key=settings.llm_api_key,
        openai_api_base=settings.llm_base_url,
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
