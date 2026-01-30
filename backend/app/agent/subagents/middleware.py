"""SubAgentMiddleware: 统一处理委派式与响应式子 Agent.

参考 deepagents SubAgentMiddleware 架构:
- 委派式: 注册 task(agent_name, description) tool，主 LLM 显式调用
- 响应式: after_model hook 自动触发，不依赖主 LLM（deepagents 扩展）
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool
from langchain.tools import tool

from app.agent.subagents.runner import SubAgentRunner
from app.agent.subagents.types import (
    CompiledSubAgent,
    ReactiveSubAgentConfig,
    SubAgentConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State Schema
# ---------------------------------------------------------------------------

class SubAgentState(AgentState):
    """扩展的 Agent State，声明 reactive 子 Agent 管理的 state keys.

    每个 reactive 子 Agent 通过 owned_state_keys 声明其管理的 key。
    新增 reactive 子 Agent 时需在此处添加对应 key 声明。
    """

    todos: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# SubAgentMiddleware
# ---------------------------------------------------------------------------

class SubAgentMiddleware(AgentMiddleware[SubAgentState]):
    """统一子 Agent Middleware.

    委派式子 Agent:
        - 构建 task(agent_name, description) tool
        - 主 LLM 调用 task() 时路由到对应子 Agent
        - 子 Agent 以隔离上下文运行，仅返回最终结果

    响应式子 Agent:
        - 在 after_model hook 中自动触发
        - context_builder 提取精简上下文
        - result_parser 解析输出为 state 更新
        - 出错时静默降级，不影响主 Agent 流程
    """

    name: str = "subagent"
    state_schema = SubAgentState

    def __init__(
        self,
        delegated: list[SubAgentConfig] | None = None,
        reactive: list[ReactiveSubAgentConfig] | None = None,
    ) -> None:
        self._runner = SubAgentRunner()

        # 预编译所有委派式子 Agent
        self._delegated: dict[str, CompiledSubAgent] = {}
        for cfg in delegated or []:
            compiled = self._runner.compile(cfg)
            self._delegated[cfg["name"]] = compiled

        # 按 trigger_hook 分组预编译响应式子 Agent
        self._reactive_by_hook: dict[
            str, list[tuple[ReactiveSubAgentConfig, CompiledSubAgent]]
        ] = {}
        for cfg in reactive or []:
            compiled = self._runner.compile(cfg)
            hook = cfg["trigger_hook"]
            self._reactive_by_hook.setdefault(hook, []).append((cfg, compiled))

        # 构建 task() tool
        self._task_tool = self._build_task_tool() if self._delegated else None

        # 日志
        n_delegated = len(self._delegated)
        n_reactive = sum(len(v) for v in self._reactive_by_hook.values())
        logger.info(
            f"SubAgentMiddleware: 初始化完成 "
            f"(delegated={n_delegated}, reactive={n_reactive})"
        )

    # ------------------------------------------------------------------
    # 公共属性: task() tool
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[BaseTool]:
        """返回需要注入主 Agent tools 列表的工具.

        使用方式 (core.py):
            all_tools = tool_registry.get_all_tools()
            all_tools.extend(subagent_mw.tools)
        """
        return [self._task_tool] if self._task_tool else []

    # ------------------------------------------------------------------
    # Middleware Hook: after_model
    # ------------------------------------------------------------------

    def after_model(self, state: SubAgentState) -> dict[str, Any] | None:
        """在主 LLM 每次输出后自动触发响应式子 Agent.

        遍历所有注册在 after_model hook 的 reactive 子 Agent:
        1. 检查 trigger_condition（如果定义）
        2. 调用 runner.invoke_reactive
        3. 合并所有 state 更新
        """
        reactive_list = self._reactive_by_hook.get("after_model")
        if not reactive_list:
            return None

        merged_updates: dict[str, Any] = {}

        for cfg, compiled in reactive_list:
            # 检查触发条件
            condition = cfg.get("trigger_condition")
            if condition is not None:
                try:
                    if not condition(state):
                        continue
                except Exception as e:
                    logger.warning(
                        f"SubAgent '{cfg['name']}': trigger_condition 异常: {e}"
                    )
                    continue

            # 调用子 Agent
            update = self._runner.invoke_reactive(compiled, state)
            if update:
                merged_updates.update(update)

        return merged_updates if merged_updates else None

    # ------------------------------------------------------------------
    # 内部: 构建 task() tool
    # ------------------------------------------------------------------

    def _build_task_tool(self) -> BaseTool:
        """构建 task(agent_name, description) 工具.

        与 deepagents 对齐:
        - agent_name: 子 Agent 名称
        - task_description: 任务描述
        - 返回子 Agent 执行结果文本
        """
        agent_list = "\n".join(
            f"  - {name}: {compiled.description}"
            for name, compiled in self._delegated.items()
        )

        # 闭包捕获
        delegated_map = self._delegated
        runner = self._runner

        @tool
        def task(agent_name: str, task_description: str) -> str:
            f"""将任务委派给专业子Agent执行。子Agent拥有独立上下文，不会污染当前对话。

可用的子Agent:
{agent_list}

参数说明：
- agent_name: 子Agent名称
- task_description: 详细的任务描述，包含所有必要上下文
"""
            if agent_name not in delegated_map:
                available = ", ".join(delegated_map.keys())
                return f"未知的子Agent '{agent_name}'。可用: {available}"

            compiled = delegated_map[agent_name]
            return runner.invoke_delegated(compiled, task_description)

        # 动态更新 description（因为 f-string in docstring 不生效）
        task.description = (
            "将任务委派给专业子Agent执行。子Agent拥有独立上下文，不会污染当前对话。\n\n"
            f"可用的子Agent:\n{agent_list}\n\n"
            "参数说明：\n"
            "- agent_name: 子Agent名称\n"
            "- task_description: 详细的任务描述，包含所有必要上下文"
        )

        return task
