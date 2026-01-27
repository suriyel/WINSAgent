"""FAISS vector store manager — dual-store for terminology & design docs."""

from __future__ import annotations

import logging
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.config import settings
from app.knowledge.loader import load_markdown_directory

logger = logging.getLogger(__name__)


def _get_embeddings() -> Embeddings:
    """Return the configured embedding model.

    Falls back to a simple fake/deterministic embedding when no API key
    is available so that the application can still boot for UI development.
    """
    if settings.llm_api_key:
        try:
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                api_key=settings.llm_api_key,
                **({"base_url": settings.llm_base_url} if settings.llm_base_url else {}),
            )
        except Exception:
            logger.warning("OpenAI embeddings unavailable, using fake embeddings")

    from langchain_core.embeddings import FakeEmbeddings
    return FakeEmbeddings(size=384)


class KnowledgeManager:
    """Manages two independent FAISS vector stores:
    - terminology_store  (专业术语表)
    - design_doc_store   (系统设计文档)
    """

    def __init__(self) -> None:
        self.embeddings: Embeddings | None = None
        self.terminology_store: FAISS | None = None
        self.design_doc_store: FAISS | None = None

    def initialize(self) -> None:
        """Build / load FAISS indexes on application startup."""
        self.embeddings = _get_embeddings()
        index_dir = Path(settings.faiss_index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)

        self.terminology_store = self._load_or_build(
            store_name="terminology",
            doc_dir=settings.terminology_dir,
        )
        self.design_doc_store = self._load_or_build(
            store_name="design_docs",
            doc_dir=settings.design_docs_dir,
        )

    def _load_or_build(self, store_name: str, doc_dir: str) -> FAISS | None:
        index_path = Path(settings.faiss_index_dir) / store_name
        assert self.embeddings is not None

        # Try loading persisted index
        if index_path.exists():
            try:
                store = FAISS.load_local(
                    str(index_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                logger.info("Loaded FAISS index: %s (%d docs)", store_name, store.index.ntotal)
                return store
            except Exception:
                logger.warning("Failed to load FAISS index %s, rebuilding", store_name)

        # Build from markdown documents
        docs = load_markdown_directory(doc_dir)
        if not docs:
            logger.info("No documents found for %s, skipping index build", store_name)
            return None

        store = FAISS.from_documents(docs, self.embeddings)
        store.save_local(str(index_path))
        logger.info("Built FAISS index: %s (%d chunks)", store_name, len(docs))
        return store

    def rebuild(self, knowledge_type: str | None = None) -> dict[str, int]:
        """Force rebuild of one or both FAISS indexes. Returns chunk counts."""
        assert self.embeddings is not None
        counts: dict[str, int] = {}

        targets: list[tuple[str, str, str]] = []
        if knowledge_type in (None, "terminology"):
            targets.append(("terminology", settings.terminology_dir, "terminology_store"))
        if knowledge_type in (None, "design_doc"):
            targets.append(("design_docs", settings.design_docs_dir, "design_doc_store"))

        for store_name, doc_dir, attr in targets:
            docs = load_markdown_directory(doc_dir)
            if docs:
                store = FAISS.from_documents(docs, self.embeddings)
                index_path = Path(settings.faiss_index_dir) / store_name
                store.save_local(str(index_path))
                setattr(self, attr, store)
                counts[store_name] = len(docs)
            else:
                counts[store_name] = 0

        return counts

    def search_terminology(self, query: str, k: int = 3) -> list[Document]:
        if self.terminology_store is None:
            return []
        return self.terminology_store.similarity_search(query, k=k)

    def search_design_docs(self, query: str, k: int = 3) -> list[Document]:
        if self.design_doc_store is None:
            return []
        return self.design_doc_store.similarity_search(query, k=k)


# Singleton
knowledge_manager = KnowledgeManager()
