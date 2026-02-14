"""Remote Reranker API client for BGE-Reranker or compatible services."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """A single reranked document with its score."""
    document: Document
    score: float
    original_index: int


class RerankerClient:
    """HTTP client for calling remote Reranker API.

    Supports OpenAI-compatible reranker endpoints (e.g. Jina, SiliconFlow,
    Xinference) that accept POST requests with query + documents.

    Expected API format:
        POST /rerank or /v1/rerank
        {
            "model": "bge-reranker-v2-m3",
            "query": "search query",
            "documents": ["doc1", "doc2", ...],
            "top_n": 3
        }

        Response:
        {
            "results": [
                {"index": 0, "relevance_score": 0.95},
                {"index": 2, "relevance_score": 0.87},
                ...
            ]
        }
    """

    def __init__(self) -> None:
        self._client: httpx.Client | None = None

    @property
    def is_configured(self) -> bool:
        return bool(settings.reranker_base_url)

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if settings.reranker_api_key:
                headers["Authorization"] = f"Bearer {settings.reranker_api_key}"
            self._client = httpx.Client(
                base_url=settings.reranker_base_url.rstrip("/"),
                headers=headers,
                timeout=30.0,
            )
        return self._client

    def rerank(
        self,
        query: str,
        candidates: list[Document],
        top_k: int = 3,
        glossary_boost_terms: list[str] | None = None,
    ) -> list[RerankResult]:
        """Rerank candidate documents using the remote API.

        Args:
            query: The search query.
            candidates: List of candidate documents from FAISS.
            top_k: Number of top results to return.
            glossary_boost_terms: Terms from the expert glossary that appear
                in the query. Documents containing these terms get a score boost.

        Returns:
            List of RerankResult sorted by score descending.
            Empty list if reranker is not configured (falls back to original order).
        """
        if not candidates:
            return []

        if not self.is_configured:
            # Fallback: return candidates in original order
            return [
                RerankResult(document=doc, score=1.0, original_index=i)
                for i, doc in enumerate(candidates[:top_k])
            ]

        doc_texts = [doc.page_content for doc in candidates]

        try:
            client = self._get_client()
            response = client.post(
                "/v1/rerank",
                json={
                    "model": settings.reranker_model,
                    "query": query,
                    "documents": doc_texts,
                    "top_n": min(top_k * 2, len(candidates)),  # Get more for glossary boost
                },
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.exception("Reranker API call failed, falling back to original order")
            return [
                RerankResult(document=doc, score=1.0, original_index=i)
                for i, doc in enumerate(candidates[:top_k])
            ]

        # Parse results
        results: list[RerankResult] = []
        for item in data.get("results", []):
            idx = item["index"]
            score = item.get("relevance_score", item.get("score", 0.0))
            if idx < len(candidates):
                results.append(RerankResult(
                    document=candidates[idx],
                    score=score,
                    original_index=idx,
                ))

        # Apply glossary boost
        if glossary_boost_terms:
            for r in results:
                content_lower = r.document.page_content.lower()
                for term in glossary_boost_terms:
                    if term.lower() in content_lower:
                        r.score *= 1.2  # 20% boost per matching term

        # Re-sort by score and return top_k
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def check_threshold(self, results: list[RerankResult]) -> bool:
        """Check if the top result exceeds the rejection threshold.

        Returns True if results are reliable, False if should reject (拒答).
        """
        if not results:
            return False
        return results[0].score >= settings.reranker_threshold


# Singleton
reranker_client = RerankerClient()
