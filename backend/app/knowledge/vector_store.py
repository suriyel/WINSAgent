"""FAISS vector store manager — dual-store for terminology & design docs + corpus store."""

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

    Uses remote OpenAI-compatible API when API key is available,
    falls back to FakeEmbeddings for UI development.
    """
    api_key = settings.effective_embedding_api_key
    base_url = settings.effective_embedding_base_url

    if api_key:
        try:
            from langchain_openai import OpenAIEmbeddings

            kwargs = {"model": settings.embedding_model, "api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            return OpenAIEmbeddings(**kwargs)
        except Exception:
            logger.warning("OpenAI embeddings unavailable, using fake embeddings")

    from langchain_core.embeddings import FakeEmbeddings
    return FakeEmbeddings(size=384)


class KnowledgeManager:
    """Manages FAISS vector stores:
    - terminology_store  (专业术语表)
    - design_doc_store   (系统设计文档)
    - corpus_store       (语料库 — 全量构建的异构文档索引)
    """

    def __init__(self) -> None:
        self.embeddings: Embeddings | None = None
        self.terminology_store: FAISS | None = None
        self.design_doc_store: FAISS | None = None
        self.corpus_store: FAISS | None = None

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

        # Load corpus index if it exists (don't auto-build — requires explicit pipeline run)
        corpus_index_path = index_dir / "corpus"
        if corpus_index_path.exists():
            try:
                self.corpus_store = FAISS.load_local(
                    str(corpus_index_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                logger.info("Loaded corpus FAISS index (%d docs)", self.corpus_store.index.ntotal)
            except Exception:
                logger.warning("Failed to load corpus FAISS index")

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

    def rebuild_corpus(self, chunks: list[Document]) -> int:
        """Build corpus FAISS index from pre-chunked documents.

        Args:
            chunks: List of Document objects from the corpus pipeline.

        Returns:
            Number of chunks indexed.
        """
        assert self.embeddings is not None

        if not chunks:
            logger.info("No corpus chunks to index")
            return 0

        # Clear existing corpus index
        corpus_index_path = Path(settings.faiss_index_dir) / "corpus"

        self.corpus_store = FAISS.from_documents(chunks, self.embeddings)
        self.corpus_store.save_local(str(corpus_index_path))
        logger.info("Built corpus FAISS index: %d chunks", len(chunks))
        return len(chunks)

    def search_terminology(self, query: str, k: int = 3) -> list[Document]:
        if self.terminology_store is None:
            return []
        return self.terminology_store.similarity_search(query, k=k)

    def search_design_docs(self, query: str, k: int = 3) -> list[Document]:
        if self.design_doc_store is None:
            return []
        return self.design_doc_store.similarity_search(query, k=k)

    def search_corpus(self, query: str, k: int = 20) -> list[Document]:
        """Search corpus store, returning top-k candidates for reranking."""
        if self.corpus_store is None:
            return []
        return self.corpus_store.similarity_search(query, k=k)


# Singleton
knowledge_manager = KnowledgeManager()
