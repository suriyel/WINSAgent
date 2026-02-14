"""FAISS retrieval tools exposed to the Agent as @tool functions."""

from __future__ import annotations

import hashlib

from langchain.tools import tool

from app.agent.tools.registry import tool_registry
from app.knowledge.vector_store import knowledge_manager
from app.knowledge.reranker import reranker_client
from app.knowledge.glossary import glossary_manager


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


@tool(response_format="content_and_artifact")
def search_corpus(query: str):
    """检索语料库中的专业文档内容。当需要查找网规网优相关的技术文档、规范、流程说明时使用此工具。

    支持高精度检索：向量召回 + 重排序 + 专家词表干预。
    返回结果包含溯源信息，可通过引用标签定位到原始文档段落。

    参数说明：
    - query: 需要检索的内容关键词或问题
    """
    # Step 1: Synonym expansion via glossary
    expanded_query = glossary_manager.expand_query(query)

    # Step 2: FAISS vector recall (top 20)
    candidates = knowledge_manager.search_corpus(expanded_query, k=20)
    if not candidates:
        return "语料库中未找到相关内容。请确认语料库已构建。", []

    # Step 3: Rerank with glossary boost
    matching_terms = glossary_manager.find_matching_terms(query)
    results = reranker_client.rerank(
        query=query,
        candidates=candidates,
        top_k=3,
        glossary_boost_terms=matching_terms,
    )

    if not results:
        return "语料库中未找到相关准确依据。", []

    # Step 4: Threshold check (拒答)
    if not reranker_client.check_threshold(results):
        return "语料库中未找到相关准确依据，系统拒绝臆断。", []

    # Step 5: Format results with traceability info
    formatted_parts = []
    for i, r in enumerate(results, 1):
        meta = r.document.metadata
        source_file = meta.get("source_file", "N/A")
        heading = meta.get("heading_path", "")
        chunk_idx = meta.get("chunk_index", 0)
        file_id = hashlib.md5(source_file.encode()).hexdigest()[:12]
        score_str = f"{r.score:.3f}" if r.score < 10 else f"{r.score:.1f}"

        formatted_parts.append(
            f"[{i}] 来源: {source_file} | 段落: {heading}\n"
            f"    相关度: {score_str} | 引用ID: {file_id}#{chunk_idx}\n"
            f"    内容: {r.document.page_content}"
        )

    serialized = "\n\n".join(formatted_parts)
    return serialized, [r.document for r in results]


def register_knowledge_tools() -> None:
    tool_registry.register(search_terminology, category="query")
    tool_registry.register(search_design_doc, category="query")
    tool_registry.register(search_corpus, category="query")
