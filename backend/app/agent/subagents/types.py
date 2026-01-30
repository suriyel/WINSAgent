"""SubAgent 类型定义.

参考 deepagents SubAgent/CompiledSubAgent 架构，
扩展 ReactiveSubAgentConfig 支持自动触发模式。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Sequence

from typing_extensions import NotRequired, TypedDict

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool


# ---------------------------------------------------------------------------
# Callable 类型别名
# ---------------------------------------------------------------------------

ContextBuilder = Callable[[dict[str, Any]], list[BaseMessage] | None]
"""从 parent state 提取精简上下文 messages 供子 Agent 使用。

Args:
    state: 主 Agent 的完整 state dict

Returns:
    消息列表（通常是单条 HumanMessage），或 None 表示跳过本次触发。
"""

ResultParser = Callable[[Any], dict[str, Any] | None]
"""解析子 Agent 输出为 state update dict。

Simple 模式: 接收 str（LLM 文本输出）
Full Agent 模式: 接收 dict（完整输出 state）

Returns:
    state 更新字典（如 {"todos": [...]}），或 None 表示无更新。
"""

TriggerCondition = Callable[[dict[str, Any]], bool]
"""判断是否触发 reactive 子 Agent。

Args:
    state: 主 Agent 的完整 state dict

Returns:
    True 表示应触发，False 表示跳过。
"""


# ---------------------------------------------------------------------------
# SubAgentConfig — 委派式子 Agent（与 deepagents SubAgent 对齐）
# ---------------------------------------------------------------------------

class SubAgentConfig(TypedDict):
    """委派式子 Agent 配置.

    通过主 Agent 的 task() tool 显式调用。
    与 deepagents 的 SubAgent TypedDict 对齐。
    """

    name: str
    """唯一标识符"""

    description: str
    """功能描述（用作 task() tool 中的子 Agent 说明）"""

    system_prompt: str
    """子 Agent 系统提示词"""

    tools: Sequence[BaseTool | Callable[..., Any]]
    """子 Agent 可用工具列表"""

    model: NotRequired[str]
    """模型标识符。为空则继承主 Agent 模型。"""

    middleware: NotRequired[list[AgentMiddleware]]
    """子 Agent 自身的 middleware 列表（不应包含 SubAgentMiddleware）"""


# ---------------------------------------------------------------------------
# ReactiveSubAgentConfig — 响应式子 Agent（deepagents 扩展）
# ---------------------------------------------------------------------------

class ReactiveSubAgentConfig(TypedDict):
    """响应式子 Agent 配置.

    由 Middleware hook 自动触发，不依赖主 LLM 显式调用。
    - 无 tools: Simple 模式（直接 LLM 调用）
    - 有 tools: Full Agent 模式（create_agent + invoke）
    """

    name: str
    """唯一标识符"""

    description: str
    """功能描述（用于日志和调试）"""

    system_prompt: str
    """子 Agent 系统提示词"""

    tools: NotRequired[Sequence[BaseTool | Callable[..., Any]]]
    """子 Agent 可用工具列表。为空则使用 Simple 模式（直接 LLM 调用）。"""

    model: NotRequired[str]
    """模型标识符。为空则继承主 Agent 模型。"""

    # ---- 触发配置 ----

    trigger_hook: Literal["after_model"]
    """触发的 Middleware hook 名称"""

    trigger_condition: NotRequired[TriggerCondition]
    """触发条件谓词。返回 True 时才执行子 Agent。
    默认: 始终触发。"""

    # ---- 上下文与结果 ----

    context_builder: ContextBuilder
    """必填。从 parent state 提取精简上下文。"""

    result_parser: NotRequired[ResultParser]
    """解析子 Agent 输出为 state 更新。Simple 模式下必填。"""

    owned_state_keys: list[str]
    """此子 Agent 管理的 state keys 列表（如 ["todos"]）。"""

    # ---- 执行限制 ----

    max_iterations: NotRequired[int]
    """Full Agent 模式的最大迭代次数。默认: 3。"""

    fallback_on_error: NotRequired[dict[str, Any]]
    """子 Agent 出错时的兜底 state 更新。默认: {} （静默忽略）。"""


# ---------------------------------------------------------------------------
# CompiledSubAgent — 编译后的子 Agent（内部实现）
# ---------------------------------------------------------------------------

@dataclass
class CompiledSubAgent:
    """编译后的子 Agent 实例.

    由 SubAgentRunner.compile() 创建。
    - Simple 模式: llm 不为 None, runnable 为 None
    - Full Agent 模式: runnable 不为 None
    """

    name: str
    description: str
    config: SubAgentConfig | ReactiveSubAgentConfig
    runnable: Any = field(default=None, repr=False)
    """Full Agent 模式: 编译后的 agent graph"""
    llm: Any = field(default=None, repr=False)
    """Simple 模式: ChatOpenAI 实例"""

    @property
    def is_simple_mode(self) -> bool:
        """是否为 Simple 模式（无 tools，直接 LLM 调用）"""
        return self.runnable is None and self.llm is not None
