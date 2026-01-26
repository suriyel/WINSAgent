"""
LLM 配置和初始化

支持:
- Qwen3-72B-Instruct via DashScope (OpenAI 兼容接口)
- 可扩展支持其他模型
"""

from functools import lru_cache
from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from app.config import get_settings


@lru_cache
def get_llm(
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> BaseChatModel:
    """
    获取 LLM 实例

    Args:
        temperature: 生成温度，默认 0.7
        max_tokens: 最大输出 token 数，默认 4096

    Returns:
        配置好的 ChatModel 实例
    """
    settings = get_settings()

    # DashScope 兼容 OpenAI 接口
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.dashscope_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return llm


def get_summarization_model() -> BaseChatModel:
    """获取用于摘要的轻量级模型"""
    settings = get_settings()

    # 摘要使用较小的 token 限制
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.dashscope_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.3,
        max_tokens=512,
    )


def get_llm_for_subagent(
    purpose: Literal["planner", "validator", "research"] = "planner"
) -> BaseChatModel:
    """
    获取用于 SubAgent 的 LLM 实例

    Args:
        purpose: SubAgent 用途，影响温度等参数

    Returns:
        配置好的 ChatModel 实例
    """
    settings = get_settings()

    # 不同用途使用不同参数
    configs = {
        "planner": {"temperature": 0.5, "max_tokens": 2048},
        "validator": {"temperature": 0.2, "max_tokens": 1024},
        "research": {"temperature": 0.6, "max_tokens": 3072},
    }

    config = configs.get(purpose, configs["planner"])

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.dashscope_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        **config,
    )
