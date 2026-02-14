"""Tests for remote Reranker API client.

验证:
- 未配置时 fallback（保持原始顺序）
- API 调用成功时正确排序
- API 失败时 fallback
- 专家词表 boost 逻辑
- 拒答阈值检查
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from langchain_core.documents import Document

from app.knowledge.reranker import RerankerClient, RerankResult


# ===========================================================================
# Helpers
# ===========================================================================

def _make_docs(n: int) -> list[Document]:
    return [
        Document(page_content=f"Document content {i}", metadata={"chunk_index": i})
        for i in range(n)
    ]


def _make_client(base_url: str = "", api_key: str = "", threshold: float = 0.3) -> RerankerClient:
    mock_settings = MagicMock()
    mock_settings.reranker_base_url = base_url
    mock_settings.reranker_api_key = api_key
    mock_settings.reranker_model = "bge-reranker-v2-m3"
    mock_settings.reranker_threshold = threshold
    with patch("app.knowledge.reranker.settings", mock_settings):
        client = RerankerClient()
        client._client = None  # Reset cached client
    return client


# ===========================================================================
# Fallback behavior (no reranker configured)
# ===========================================================================

class TestFallback:

    def test_no_config_returns_original_order(self):
        client = _make_client(base_url="")
        docs = _make_docs(5)
        with patch("app.knowledge.reranker.settings") as mock_s:
            mock_s.reranker_base_url = ""
            mock_s.reranker_threshold = 0.3
            results = client.rerank("query", docs, top_k=3)

        assert len(results) == 3
        assert results[0].document.page_content == "Document content 0"
        assert all(r.score == 1.0 for r in results)

    def test_empty_candidates(self):
        client = _make_client(base_url="http://example.com")
        with patch("app.knowledge.reranker.settings") as mock_s:
            mock_s.reranker_base_url = "http://example.com"
            results = client.rerank("query", [], top_k=3)
        assert results == []


# ===========================================================================
# API call with mock httpx
# ===========================================================================

class TestApiCall:

    def test_successful_rerank(self):
        client = _make_client(base_url="http://reranker.local")
        docs = _make_docs(5)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"index": 3, "relevance_score": 0.95},
                {"index": 1, "relevance_score": 0.80},
                {"index": 0, "relevance_score": 0.60},
            ]
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        client._client = mock_client

        with patch("app.knowledge.reranker.settings") as mock_s:
            mock_s.reranker_base_url = "http://reranker.local"
            mock_s.reranker_model = "bge-reranker-v2-m3"
            mock_s.reranker_threshold = 0.3
            results = client.rerank("query", docs, top_k=3)

        assert len(results) == 3
        # Should be sorted by score descending
        assert results[0].score == 0.95
        assert results[0].document.page_content == "Document content 3"
        assert results[1].score == 0.80
        assert results[2].score == 0.60

    def test_api_error_fallback(self):
        client = _make_client(base_url="http://reranker.local")
        docs = _make_docs(5)

        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("Connection refused")
        client._client = mock_client

        with patch("app.knowledge.reranker.settings") as mock_s:
            mock_s.reranker_base_url = "http://reranker.local"
            mock_s.reranker_model = "bge-reranker-v2-m3"
            mock_s.reranker_threshold = 0.3
            results = client.rerank("query", docs, top_k=3)

        # Should fallback to original order
        assert len(results) == 3
        assert all(r.score == 1.0 for r in results)


# ===========================================================================
# Glossary boost
# ===========================================================================

class TestGlossaryBoost:

    def test_boost_matching_terms(self):
        client = _make_client(base_url="http://reranker.local")
        docs = [
            Document(page_content="RSRP 指标分析说明", metadata={}),
            Document(page_content="天线朝向调整方案", metadata={}),
            Document(page_content="RSRP 弱覆盖优化", metadata={}),
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"index": 0, "relevance_score": 0.70},
                {"index": 1, "relevance_score": 0.75},  # Higher before boost
                {"index": 2, "relevance_score": 0.65},
            ]
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        client._client = mock_client

        with patch("app.knowledge.reranker.settings") as mock_s:
            mock_s.reranker_base_url = "http://reranker.local"
            mock_s.reranker_model = "bge-reranker-v2-m3"
            mock_s.reranker_threshold = 0.3
            results = client.rerank("RSRP", docs, top_k=3, glossary_boost_terms=["RSRP"])

        # Documents containing "RSRP" should be boosted
        rsrp_results = [r for r in results if "RSRP" in r.document.page_content]
        non_rsrp = [r for r in results if "RSRP" not in r.document.page_content]
        # Boosted RSRP docs should rank higher
        assert rsrp_results[0].score > non_rsrp[0].score


# ===========================================================================
# Threshold check
# ===========================================================================

class TestCheckThreshold:

    def test_above_threshold(self):
        client = _make_client(threshold=0.3)
        results = [RerankResult(document=Document(page_content=""), score=0.5, original_index=0)]
        with patch("app.knowledge.reranker.settings") as mock_s:
            mock_s.reranker_threshold = 0.3
            assert client.check_threshold(results) is True

    def test_below_threshold(self):
        client = _make_client(threshold=0.3)
        results = [RerankResult(document=Document(page_content=""), score=0.1, original_index=0)]
        with patch("app.knowledge.reranker.settings") as mock_s:
            mock_s.reranker_threshold = 0.3
            assert client.check_threshold(results) is False

    def test_empty_results(self):
        client = _make_client(threshold=0.3)
        with patch("app.knowledge.reranker.settings") as mock_s:
            mock_s.reranker_threshold = 0.3
            assert client.check_threshold([]) is False

    def test_exactly_at_threshold(self):
        client = _make_client(threshold=0.3)
        results = [RerankResult(document=Document(page_content=""), score=0.3, original_index=0)]
        with patch("app.knowledge.reranker.settings") as mock_s:
            mock_s.reranker_threshold = 0.3
            assert client.check_threshold(results) is True
