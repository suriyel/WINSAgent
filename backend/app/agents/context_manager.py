"""
上下文管理模块
负责消息历史压缩、token预算控制、工具调用元数据裁剪
"""

from typing import List
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from tiktoken import encoding_for_model

from .state import AgentState, TodoStep


class ContextManager:
    """上下文管理器 - 处理消息历史压缩和token预算"""

    def __init__(self, max_tokens: int = 4000):
        """
        初始化上下文管理器

        Args:
            max_tokens: 最大token数量（默认4000）
        """
        self.max_tokens = max_tokens
        # 使用 gpt-3.5-turbo 的编码器估算 token（与 Qwen 类似）
        try:
            self.encoding = encoding_for_model("gpt-3.5-turbo")
        except Exception:
            # 如果失败，使用 cl100k_base 编码器
            from tiktoken import get_encoding
            self.encoding = get_encoding("cl100k_base")

    def count_tokens(self, messages: List[BaseMessage]) -> int:
        """
        计算消息列表的token数量

        Args:
            messages: 消息列表

        Returns:
            总token数
        """
        total_tokens = 0
        for msg in messages:
            # 计算消息内容的token
            if hasattr(msg, 'content') and msg.content:
                total_tokens += len(self.encoding.encode(str(msg.content)))

            # 添加消息类型的开销（约4个token per message）
            total_tokens += 4

            # Tool call 额外开销
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    total_tokens += len(self.encoding.encode(str(tool_call)))

        return total_tokens

    def compress_completed_steps(
        self,
        messages: List[BaseMessage],
        todo_list: List[TodoStep]
    ) -> List[BaseMessage]:
        """
        压缩已完成步骤的消息历史
        将已完成步骤的 tool call + tool result 替换为简短摘要

        Args:
            messages: 原始消息列表
            todo_list: 任务步骤列表

        Returns:
            压缩后的消息列表
        """
        # 获取已完成步骤的ID集合
        completed_step_ids = {
            step["id"] for step in todo_list
            if step["status"] == "completed"
        }

        compressed = []
        i = 0

        while i < len(messages):
            msg = messages[i]

            # 检查是否是 AI 消息且有 tool_calls
            if (
                isinstance(msg, AIMessage)
                and hasattr(msg, "tool_calls")
                and msg.tool_calls
            ):
                # 检查下一条是否是对应的 ToolMessage
                if i + 1 < len(messages) and isinstance(messages[i + 1], ToolMessage):
                    tool_call = msg.tool_calls[0]
                    tool_result = messages[i + 1]

                    # 检查该 tool call 是否属于已完成步骤
                    # 简化：如果 tool_result 存在，则认为该步骤已完成
                    if tool_result.content:
                        # 替换为压缩摘要
                        summary = f"[已执行] {tool_call['name']} → 结果: {str(tool_result.content)[:100]}..."
                        compressed.append(
                            AIMessage(content=summary)
                        )
                        i += 2  # 跳过 tool_call 和 tool_result
                        continue

            # 保留其他消息
            compressed.append(msg)
            i += 1

        return compressed

    def trim_tool_metadata(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        裁剪工具调用元数据
        移除已执行工具的内部ID、中间状态等非必要信息

        Args:
            messages: 原始消息列表

        Returns:
            裁剪后的消息列表
        """
        trimmed = []

        for msg in messages:
            # 如果是 ToolMessage，简化内容
            if isinstance(msg, ToolMessage):
                # 保留结果，但移除冗长的元数据
                simplified = ToolMessage(
                    content=str(msg.content)[:500] if msg.content else "",  # 限制长度
                    tool_call_id=msg.tool_call_id,
                )
                trimmed.append(simplified)

            # 如果是 AIMessage with tool_calls，保留但简化
            elif isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                # 创建简化版本的 tool_calls
                simplified_calls = []
                for call in msg.tool_calls:
                    # 只保留必要字段
                    simplified_calls.append({
                        "name": call.get("name"),
                        "args": call.get("args", {}),
                        "id": call.get("id"),
                    })

                # 创建新的 AIMessage
                new_msg = AIMessage(
                    content=msg.content or "",
                )
                new_msg.tool_calls = simplified_calls
                trimmed.append(new_msg)

            else:
                # 其他消息保持不变
                trimmed.append(msg)

        return trimmed

    def enforce_token_budget(
        self,
        messages: List[BaseMessage],
        system_prompt_tokens: int = 500,
        knowledge_tokens: int = 1500,
        response_tokens: int = 500,
    ) -> List[BaseMessage]:
        """
        强制执行token预算
        如果超出预算，从历史消息中间开始删除（保留最新和最早的消息）

        Args:
            messages: 消息列表
            system_prompt_tokens: 系统提示预留token
            knowledge_tokens: 知识上下文预留token
            response_tokens: 响应空间预留token

        Returns:
            裁剪后的消息列表
        """
        reserved_tokens = system_prompt_tokens + knowledge_tokens + response_tokens
        available_tokens = self.max_tokens - reserved_tokens

        current_tokens = self.count_tokens(messages)

        # 如果在预算内，直接返回
        if current_tokens <= available_tokens:
            return messages

        # 超出预算，需要裁剪
        # 策略：保留第一条（通常是用户初始输入）和最后N条消息
        if len(messages) <= 2:
            return messages

        # 保留第一条消息
        first_msg = [messages[0]] if messages else []

        # 从最后开始累积，直到达到预算
        last_msgs = []
        accumulated_tokens = self.count_tokens(first_msg)

        for msg in reversed(messages[1:]):
            msg_tokens = self.count_tokens([msg])
            if accumulated_tokens + msg_tokens <= available_tokens:
                last_msgs.insert(0, msg)
                accumulated_tokens += msg_tokens
            else:
                break

        # 添加摘要消息表示已裁剪
        trimmed_count = len(messages) - len(first_msg) - len(last_msgs)
        if trimmed_count > 0:
            summary_msg = SystemMessage(
                content=f"[上下文已压缩：省略了 {trimmed_count} 条中间消息以控制token预算]"
            )
            result = first_msg + [summary_msg] + last_msgs
        else:
            result = first_msg + last_msgs

        return result

    def optimize_context(
        self,
        state: AgentState,
        system_prompt_tokens: int = 500,
        knowledge_tokens: int = 1500,
        response_tokens: int = 500,
    ) -> List[BaseMessage]:
        """
        综合优化上下文
        按顺序应用：1. 压缩已完成步骤 2. 裁剪工具元数据 3. 强制token预算

        Args:
            state: Agent状态
            system_prompt_tokens: 系统提示预留token
            knowledge_tokens: 知识上下文预留token
            response_tokens: 响应空间预留token

        Returns:
            优化后的消息列表
        """
        messages = state.get("messages", [])
        todo_list = state.get("todo_list", [])

        # 步骤1: 压缩已完成步骤
        messages = self.compress_completed_steps(messages, todo_list)

        # 步骤2: 裁剪工具元数据
        messages = self.trim_tool_metadata(messages)

        # 步骤3: 强制token预算
        messages = self.enforce_token_budget(
            messages,
            system_prompt_tokens,
            knowledge_tokens,
            response_tokens,
        )

        return messages


# 全局单例
_context_manager = None


def get_context_manager(max_tokens: int = 4000) -> ContextManager:
    """获取上下文管理器单例"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager(max_tokens)
    return _context_manager
