"""Agent core: builds the main Agent with middleware and tools."""

from __future__ import annotations

from langchain.agents.middleware import ContextEditingMiddleware, ClearToolUsesEdit
from langgraph.store.memory import InMemoryStore
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.callbacks import BaseCallbackHandler
from app.agent.middleware.chart_data import ChartDataMiddleware
from app.agent.middleware.data_table import DataTableMiddleware
from app.agent.middleware.missing_params import MissingParamsMiddleware
from app.agent.middleware.skill import SkillMiddleware
from app.agent.middleware.suggestions import SuggestionsMiddleware
from app.agent.prompts.base_prompt import BASE_SYSTEM_PROMPT
from app.agent.subagents import SubAgentMiddleware
from app.agent.subagents.agents.todo_tracker import TODO_TRACKER_CONFIG
from app.agent.tools.telecom_tools import register_telecom_tools
from app.agent.tools.hil import CustomHumanInTheLoopMiddleware
from app.agent.tools.knowledge import register_knowledge_tools
from app.agent.tools.registry import tool_registry
from app.config import settings
import json
import logging

logger = logging.getLogger("llm_logger")
logger.setLevel(logging.INFO)
# 控制台
console = logging.StreamHandler()
logger.addHandler(console)

# In-memory checkpointer for dev/validation stage
_checkpointer = InMemorySaver()
_storage = InMemoryStore()

# Track whether tools have been registered
_initialized = False

class LLMRequestLogger(BaseCallbackHandler):

    def on_llm_start(self, serialized, prompts, **kwargs):
        logger.info("====== LLM REQUEST START ======")
        logger.info("Serialized model: %s", json.dumps(serialized, indent=2, ensure_ascii=False))

        for i, prompt in enumerate(prompts):
            logger.info("Prompt %d:\n%s", i, prompt)

        if "invocation_params" in kwargs:
            logger.info(
                "Invocation params: %s",
                json.dumps(kwargs["invocation_params"], indent=2, ensure_ascii=False)
            )

        logger.info("====== LLM REQUEST END ======")

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

    # Skill Middleware（动态加载 Skill 内容到 SYSTEM_PROMPT）
    skill_mw = SkillMiddleware(
        skills_dir=settings.skills_dir,
        base_prompt_template=BASE_SYSTEM_PROMPT,
    )
    # 注入 select_skill tool
    all_tools.extend(skill_mw.tools)

    # SubAgent Middleware（替代 TodoListMiddleware）
    subagent_mw = SubAgentMiddleware(
        delegated=[],
        reactive=[TODO_TRACKER_CONFIG],
    )
    # 注入 task() tool（如有委派式子 Agent）
    all_tools.extend(subagent_mw.tools)

    middleware = [
        skill_mw,  # Skill 选择（最高优先级，控制 tools 和 system_prompt）
        subagent_mw,
        DataTableMiddleware(),
        ChartDataMiddleware(),
        SuggestionsMiddleware(),
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger=3000,
                    keep=2,
                    clear_tool_inputs=True,
                    exclude_tools=[
                        'search_design_doc',
                        'search_terminology',
                        'select_skill',  # 不清理 Skill 选择记录
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

    # 配置 LLM
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        streaming=True,
        callbacks=[LLMRequestLogger()]
    )

    # 使用动态 SYSTEM_PROMPT（通过 SkillMiddleware 的 Jinja2 模板渲染注入 Skill 内容）
    agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=BASE_SYSTEM_PROMPT,  # Jinja2 模板，运行时由 SkillMiddleware 动态渲染
        middleware=middleware,
        checkpointer=_checkpointer,
        store=_storage,
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
