"""
上下文管理中间件

基于 LangGraph pre_model_hook 实现:
1. Token 预算控制 - 裁剪超长历史
2. 工具消息压缩 - 压缩已完成的工具调用结果
3. 保留关键信息 - 首条消息 + 最近消息
"""

from dataclasses import dataclass
from typing import Callable, Any

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
    RemoveMessage,
)
from langchain_core.messages.utils import trim_messages, count_tokens_approximately
from langchain_core.language_models import BaseChatModel


@dataclass
class ContextConfig:
    """上下文管理配置"""

    max_tokens: int = 4000
    """最大 token 数"""

    max_tokens_before_summary: int = 6000
    """触发摘要的 token 阈值"""

    max_summary_tokens: int = 512
    """摘要最大 token 数"""

    preserve_recent_messages: int = 10
    """保留最近 N 条消息"""

    compress_tool_results: bool = True
    """是否压缩工具结果"""

    tool_result_max_length: int = 500
    """工具结果最大长度"""


def create_context_middleware(
    config: ContextConfig | None = None,
    summarization_model: BaseChatModel | None = None,
) -> Callable:
    """
    创建上下文管理中间件

    Args:
        config: 上下文配置
        summarization_model: 用于摘要的模型 (可选)

    Returns:
        pre_model_hook 函数
    """
    if config is None:
        config = ContextConfig()

    def middleware(state: dict[str, Any]) -> dict[str, Any]:
        """
        pre_model_hook 实现

        返回格式:
        - llm_input_messages: 用于 LLM 输入的消息 (不修改原始 state)
        - 或 messages: 直接更新 state 中的消息
        """
        messages = state.get("messages", [])

        if not messages:
            return {"llm_input_messages": []}

        # 1. 压缩工具结果
        if config.compress_tool_results:
            messages = _compress_tool_messages(messages, config.tool_result_max_length)

        # 2. 计算当前 token 数
        current_tokens = count_tokens_approximately(messages)

        # 3. 如果超过阈值，进行裁剪
        if current_tokens > config.max_tokens:
            messages = _trim_messages_smart(
                messages,
                max_tokens=config.max_tokens,
                preserve_recent=config.preserve_recent_messages,
            )

        return {"llm_input_messages": messages}

    return middleware


def _compress_tool_messages(
    messages: list[BaseMessage],
    max_length: int = 500,
) -> list[BaseMessage]:
    """
    压缩工具消息

    对于已完成的工具调用，截断过长的结果
    """
    compressed = []

    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = msg.content
            if isinstance(content, str) and len(content) > max_length:
                # 截断并添加省略标记
                truncated = content[:max_length] + f"\n... [已截断，原长度: {len(content)}]"
                compressed.append(
                    ToolMessage(
                        content=truncated,
                        tool_call_id=msg.tool_call_id,
                        name=msg.name,
                    )
                )
            else:
                compressed.append(msg)
        else:
            compressed.append(msg)

    return compressed


def _trim_messages_smart(
    messages: list[BaseMessage],
    max_tokens: int,
    preserve_recent: int = 10,
) -> list[BaseMessage]:
    """
    智能裁剪消息

    策略:
    1. 保留 SystemMessage (如果有)
    2. 保留首条用户消息 (建立上下文)
    3. 保留最近 N 条消息
    4. 中间消息按 token 预算裁剪
    """
    if not messages:
        return []

    # 分离系统消息
    system_messages = [m for m in messages if isinstance(m, SystemMessage)]
    non_system = [m for m in messages if not isinstance(m, SystemMessage)]

    if not non_system:
        return system_messages

    # 保留首条和最近消息
    first_message = non_system[0] if non_system else None
    recent_messages = non_system[-preserve_recent:] if len(non_system) > preserve_recent else non_system

    # 如果首条消息不在最近消息中，单独保留
    if first_message and first_message not in recent_messages:
        preserved = [first_message] + recent_messages
    else:
        preserved = recent_messages

    # 组合：系统消息 + 保留的消息
    result = system_messages + preserved

    # 最终 token 检查，使用 trim_messages 确保不超限
    return trim_messages(
        result,
        max_tokens=max_tokens,
        strategy="last",
        token_counter=count_tokens_approximately,
        include_system=True,
        start_on="human",
        end_on=("human", "tool"),
        allow_partial=False,
    )


def create_overwrite_middleware(
    max_tokens: int = 4000,
) -> Callable:
    """
    创建覆盖式上下文中间件

    与普通中间件不同，这个会直接覆盖 state 中的 messages，
    用于需要持久化裁剪结果的场景。
    """
    from langgraph.graph.message import REMOVE_ALL_MESSAGES

    def middleware(state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])

        if not messages:
            return {}

        trimmed = trim_messages(
            messages,
            strategy="last",
            token_counter=count_tokens_approximately,
            max_tokens=max_tokens,
            start_on="human",
            end_on=("human", "tool"),
            include_system=True,
        )

        # 返回 RemoveMessage 指令 + 新消息，覆盖历史
        return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)] + trimmed}

    return middleware
