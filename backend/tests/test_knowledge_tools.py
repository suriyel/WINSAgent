"""Tests for search_corpus tool in knowledge.py.

验证:
- 词表扩展 → FAISS 召回 → Reranker 重排 → 阈值检查 → 格式化输出
- 语料库为空时返回提示
- Reranker 拒答（低分）时返回拒答消息
- 结果包含溯源信息（file_id#chunk_idx）
"""

from __future__ import annotations

import hashlib
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.documents import Document

from app.knowledge.reranker import RerankResult


# ===========================================================================
# Helpers
# ===========================================================================

def _make_doc(content: str, source_file: str = "test.md", chunk_index: int = 0,
              heading_path: str = "# Title") -> Document:
    return Document(
        page_content=content,
        metadata={
            "source_file": source_file,
            "heading_path": heading_path,
            "chunk_index": chunk_index,
            "has_images": False,
        },
    )


def _make_rerank_result(doc: Document, score: float, idx: int = 0) -> RerankResult:
    return RerankResult(document=doc, score=score, original_index=idx)


def _invoke_search(query: str):
    """Invoke search_corpus tool and return the content string."""
    from app.agent.tools.knowledge import search_corpus
    return search_corpus.invoke({"query": query})


# ===========================================================================
# Tests
# ===========================================================================

class TestSearchCorpus:

    def test_empty_corpus_returns_hint(self):
        """No candidates from FAISS → prompt to build."""
        with patch("app.agent.tools.knowledge.glossary_manager") as mock_gm, \
             patch("app.agent.tools.knowledge.knowledge_manager") as mock_km:
            mock_gm.expand_query.return_value = "RSRP"
            mock_km.search_corpus.return_value = []

            content = _invoke_search("RSRP")

        assert "未找到" in content
        assert "语料库已构建" in content

    def test_reranker_returns_empty(self):
        """Reranker returns empty list → no accurate evidence."""
        doc = _make_doc("some content")
        with patch("app.agent.tools.knowledge.glossary_manager") as mock_gm, \
             patch("app.agent.tools.knowledge.knowledge_manager") as mock_km, \
             patch("app.agent.tools.knowledge.reranker_client") as mock_rr:
            mock_gm.expand_query.return_value = "RSRP"
            mock_gm.find_matching_terms.return_value = []
            mock_km.search_corpus.return_value = [doc]
            mock_rr.rerank.return_value = []

            content = _invoke_search("RSRP")

        assert "未找到相关准确依据" in content

    def test_below_threshold_refuses(self):
        """Rerank score below threshold → refusal message."""
        doc = _make_doc("低相关内容", source_file="low.md")
        rr_result = _make_rerank_result(doc, score=0.1)

        with patch("app.agent.tools.knowledge.glossary_manager") as mock_gm, \
             patch("app.agent.tools.knowledge.knowledge_manager") as mock_km, \
             patch("app.agent.tools.knowledge.reranker_client") as mock_rr:
            mock_gm.expand_query.return_value = "RSRP"
            mock_gm.find_matching_terms.return_value = []
            mock_km.search_corpus.return_value = [doc]
            mock_rr.rerank.return_value = [rr_result]
            mock_rr.check_threshold.return_value = False

            content = _invoke_search("RSRP")

        assert "拒绝臆断" in content

    def test_successful_search_with_traceability(self):
        """Full pipeline success → formatted results with file_id#chunk_idx."""
        doc1 = _make_doc("RSRP 参考信号接收功率", source_file="telecom.md",
                         chunk_index=5, heading_path="# 指标 > ## RSRP")
        doc2 = _make_doc("SINR 信干噪比", source_file="telecom.md",
                         chunk_index=8, heading_path="# 指标 > ## SINR")
        results = [
            _make_rerank_result(doc1, score=0.95, idx=0),
            _make_rerank_result(doc2, score=0.82, idx=1),
        ]

        with patch("app.agent.tools.knowledge.glossary_manager") as mock_gm, \
             patch("app.agent.tools.knowledge.knowledge_manager") as mock_km, \
             patch("app.agent.tools.knowledge.reranker_client") as mock_rr:
            mock_gm.expand_query.return_value = "RSRP 参考信号接收功率"
            mock_gm.find_matching_terms.return_value = ["RSRP"]
            mock_km.search_corpus.return_value = [doc1, doc2]
            mock_rr.rerank.return_value = results
            mock_rr.check_threshold.return_value = True

            content = _invoke_search("RSRP")

        # Should contain traceability info
        assert "telecom.md" in content
        assert "RSRP" in content
        assert "#5" in content  # chunk_index anchor
        assert "0.950" in content  # score formatting

    def test_glossary_expansion_is_used(self):
        """Verify expanded query is passed to FAISS, not the raw query."""
        doc = _make_doc("content")
        rr = _make_rerank_result(doc, score=0.9)

        with patch("app.agent.tools.knowledge.glossary_manager") as mock_gm, \
             patch("app.agent.tools.knowledge.knowledge_manager") as mock_km, \
             patch("app.agent.tools.knowledge.reranker_client") as mock_rr:
            mock_gm.expand_query.return_value = "参考信号接收功率 RSRP"
            mock_gm.find_matching_terms.return_value = []
            mock_km.search_corpus.return_value = [doc]
            mock_rr.rerank.return_value = [rr]
            mock_rr.check_threshold.return_value = True

            _invoke_search("RSRP")

        # FAISS should receive the expanded query
        mock_km.search_corpus.assert_called_once_with("参考信号接收功率 RSRP", k=20)

    def test_matching_terms_passed_to_reranker(self):
        """Verify glossary matching terms are forwarded to reranker for boost."""
        doc = _make_doc("content")
        rr = _make_rerank_result(doc, score=0.9)

        with patch("app.agent.tools.knowledge.glossary_manager") as mock_gm, \
             patch("app.agent.tools.knowledge.knowledge_manager") as mock_km, \
             patch("app.agent.tools.knowledge.reranker_client") as mock_rr:
            mock_gm.expand_query.return_value = "query"
            mock_gm.find_matching_terms.return_value = ["RSRP", "SINR"]
            mock_km.search_corpus.return_value = [doc]
            mock_rr.rerank.return_value = [rr]
            mock_rr.check_threshold.return_value = True

            _invoke_search("RSRP SINR")

        mock_rr.rerank.assert_called_once()
        call_kwargs = mock_rr.rerank.call_args
        assert call_kwargs.kwargs.get("glossary_boost_terms") == ["RSRP", "SINR"] or \
               call_kwargs[1].get("glossary_boost_terms") == ["RSRP", "SINR"]

    def test_file_id_hash_format(self):
        """Verify file_id is a 12-char MD5 prefix of the source filename."""
        source_file = "网规文档.md"
        expected_id = hashlib.md5(source_file.encode()).hexdigest()[:12]

        doc = _make_doc("content", source_file=source_file, chunk_index=3)
        rr = _make_rerank_result(doc, score=0.9)

        with patch("app.agent.tools.knowledge.glossary_manager") as mock_gm, \
             patch("app.agent.tools.knowledge.knowledge_manager") as mock_km, \
             patch("app.agent.tools.knowledge.reranker_client") as mock_rr:
            mock_gm.expand_query.return_value = "query"
            mock_gm.find_matching_terms.return_value = []
            mock_km.search_corpus.return_value = [doc]
            mock_rr.rerank.return_value = [rr]
            mock_rr.check_threshold.return_value = True

            content = _invoke_search("test")

        assert f"{expected_id}#3" in content
