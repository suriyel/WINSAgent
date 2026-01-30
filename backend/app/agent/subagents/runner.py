"""SubAgentRunner: 编译并调用子 Agent.

支持两种执行模式:
- Simple 模式: 无 tools 时直接 llm.invoke()，快速轻量
- Full Agent 模式: 有 tools 时 create_agent + agent.invoke()，完整代理循环
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.agent.subagents.types import (
    CompiledSubAgent,
    ReactiveSubAgentConfig,
    SubAgentConfig,
)
from app.config import settings

logger = logging.getLogger(__name__)


class SubAgentRunner:
    """子 Agent 编译与调用引擎.

    - compile(): 将配置编译为 CompiledSubAgent（缓存）
    - invoke_delegated(): 委派模式调用（状态隔离，返回文本）
    - invoke_reactive(): 响应模式调用（不抛异常，返回 state 更新）
    """

    def __init__(self) -> None:
        self._compiled: dict[str, CompiledSubAgent] = {}
        self._llm_cache: dict[str, ChatOpenAI] = {}

    # ------------------------------------------------------------------
    # 编译
    # ------------------------------------------------------------------

    def compile(
        self, config: SubAgentConfig | ReactiveSubAgentConfig
    ) -> CompiledSubAgent:
        """编译子 Agent 配置为可执行实例.

        根据 config 中是否有 tools 自动选择 Simple / Full Agent 模式。
        结果会缓存，同名子 Agent 只编译一次。
        """
        name = config["name"]
        if name in self._compiled:
            return self._compiled[name]

        llm = self._get_or_create_llm(config.get("model"))
        tools = list(config.get("tools") or [])

        if tools:
            # Full Agent 模式
            agent = create_agent(
                model=llm,
                tools=tools,
                system_prompt=config["system_prompt"],
                middleware=config.get("middleware", []),
            )
            compiled = CompiledSubAgent(
                name=name,
                description=config["description"],
                config=config,
                runnable=agent,
            )
        else:
            # Simple 模式（直接 LLM 调用）
            compiled = CompiledSubAgent(
                name=name,
                description=config["description"],
                config=config,
                llm=llm,
            )

        self._compiled[name] = compiled
        logger.info(
            f"SubAgentRunner: 编译子 Agent '{name}' "
            f"({'Simple' if compiled.is_simple_mode else 'Full Agent'} 模式)"
        )
        return compiled

    # ------------------------------------------------------------------
    # 委派模式调用
    # ------------------------------------------------------------------

    def invoke_delegated(
        self,
        compiled: CompiledSubAgent,
        task_description: str,
    ) -> str:
        """委派调用: 状态隔离，仅传入 HumanMessage，返回文本结果.

        遵循 deepagents 的状态隔离模式:
        - 过滤 parent 的 messages/todos 等
        - 仅传入 task_description 作为 HumanMessage
        - 仅返回最终 AIMessage 内容
        """
        if compiled.runnable is None:
            return f"子 Agent '{compiled.name}' 未编译为 Full Agent 模式，无法委派调用。"

        try:
            result = compiled.runnable.invoke(
                {"messages": [HumanMessage(content=task_description)]}
            )
            return self._extract_last_ai_content(result)
        except Exception as e:
            logger.error(
                f"SubAgentRunner: 委派子 Agent '{compiled.name}' 失败: {e}",
                exc_info=True,
            )
            return f"子 Agent 执行出错: {e}"

    # ------------------------------------------------------------------
    # 响应模式调用
    # ------------------------------------------------------------------

    def invoke_reactive(
        self,
        compiled: CompiledSubAgent,
        parent_state: dict[str, Any],
    ) -> dict[str, Any]:
        """响应式调用: 自动触发，不抛异常，返回 state 更新 dict.

        1. context_builder 提取精简上下文
        2. Simple 模式: 直接 llm.invoke()
           Full Agent 模式: agent.invoke()
        3. result_parser 解析输出为 state 更新
        """
        config = compiled.config
        name = compiled.name
        fallback: dict[str, Any] = config.get("fallback_on_error", {})

        # Step 1: 提取上下文
        context_builder = config.get("context_builder")
        if context_builder is None:
            logger.warning(f"SubAgent '{name}': 缺少 context_builder")
            return fallback

        try:
            context_messages = context_builder(parent_state)
        except Exception as e:
            logger.warning(f"SubAgent '{name}': context_builder 异常: {e}")
            return fallback

        if not context_messages:
            return {}

        # Step 2: 调用子 Agent
        try:
            if compiled.is_simple_mode:
                raw_output = self._invoke_simple(compiled, context_messages)
            else:
                raw_output = self._invoke_full(compiled, context_messages)
        except Exception as e:
            logger.warning(f"SubAgent '{name}': 调用失败: {e}", exc_info=True)
            return fallback

        # Step 3: 解析结果
        result_parser = config.get("result_parser")
        if result_parser:
            try:
                parsed = result_parser(raw_output)
                return parsed if isinstance(parsed, dict) else {}
            except Exception as e:
                logger.warning(f"SubAgent '{name}': result_parser 异常: {e}")
                return fallback

        # 无 parser 时：Full Agent 模式下尝试提取 owned keys
        if isinstance(raw_output, dict):
            owned_keys = config.get("owned_state_keys", [])
            return {k: raw_output[k] for k in owned_keys if k in raw_output}

        return {}

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _invoke_simple(
        self,
        compiled: CompiledSubAgent,
        context_messages: list,
    ) -> str:
        """Simple 模式: 直接 LLM 调用.

        Returns:
            LLM 输出的文本内容
        """
        system_msg = {"role": "system", "content": compiled.config["system_prompt"]}
        response = compiled.llm.invoke([system_msg] + context_messages)
        content = response.content if hasattr(response, "content") else str(response)
        return content if isinstance(content, str) else str(content)

    def _invoke_full(
        self,
        compiled: CompiledSubAgent,
        context_messages: list,
    ) -> dict[str, Any]:
        """Full Agent 模式: create_agent + invoke.

        Returns:
            子 Agent 的完整输出 state dict
        """
        return compiled.runnable.invoke({"messages": context_messages})

    def _get_or_create_llm(self, model: str | None = None) -> ChatOpenAI:
        """获取或创建 LLM 实例（按 model 标识缓存）."""
        model_id = model or settings.subagent_model or settings.llm_model
        if model_id not in self._llm_cache:
            self._llm_cache[model_id] = ChatOpenAI(
                model=model_id,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                streaming=False,  # 子 Agent 不直接向前端流式输出
            )
            logger.info(f"SubAgentRunner: 创建 LLM 实例 model={model_id}")
        return self._llm_cache[model_id]

    @staticmethod
    def _extract_last_ai_content(result: dict[str, Any]) -> str:
        """从 agent invoke 结果中提取最后一条 AIMessage 内容."""
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                content = msg.content
                return content if isinstance(content, str) else str(content)
        return "子 Agent 执行完成但未产生回复。"
