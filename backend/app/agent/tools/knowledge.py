"""FAISS retrieval tools exposed to the Agent as @tool functions."""

from __future__ import annotations

from langchain.tools import tool

from app.agent.tools.registry import tool_registry
from app.knowledge.vector_store import knowledge_manager


@tool(response_format="content_and_artifact")
def search_terminology(query: str):
    """当遇到专业术语或需要查询术语定义时，使用此工具检索专业术语表。

    参数说明：
    - query: 需要检索的术语或关键词
    """
    docs = knowledge_manager.search_terminology(query, k=3)
    if not docs:
        return "未找到相关术语。", []
    serialized = "\n\n".join(
        f"术语来源: {doc.metadata.get('source', 'N/A')}\n内容: {doc.page_content}"
        for doc in docs
    )
    return serialized, docs


@tool(response_format="content_and_artifact")
def search_design_doc(query: str):
    """当需要了解存量系统设计、接口规范或架构信息时，使用此工具检索系统设计文档。

    参数说明：
    - query: 需要检索的设计内容关键词
    """
    docs = knowledge_manager.search_design_docs(query, k=3)
    if not docs:
        return "未找到相关设计文档。", []
    serialized = "\n\n".join(
        f"文档来源: {doc.metadata.get('source', 'N/A')}\n内容: {doc.page_content}"
        for doc in docs
    )
    return serialized, docs


def register_knowledge_tools() -> None:
    tool_registry.register(search_terminology, category="query")
    tool_registry.register(search_design_doc, category="query")
