"""
LLM 配置和初始化
"""

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from functools import lru_cache

from app.config import get_settings


@lru_cache
def get_llm() -> BaseChatModel:
    """获取 LLM 实例 (Qwen3-72B-Instruct via DashScope)"""
    settings = get_settings()

    # DashScope 兼容 OpenAI 接口
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.dashscope_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.7,
        max_tokens=4096,
    )

    return llm


def get_llm_with_tools(tools: list) -> BaseChatModel:
    """获取绑定工具的 LLM"""
    llm = get_llm()
    return llm.bind_tools(tools)
