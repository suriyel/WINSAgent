"""Tests for expert glossary manager.

验证:
- JSON 词表加载（术语 + 同义词）
- CSV 词表加载
- 查询扩展（同义词展开）
- 术语匹配检测
- reload 清空并重新加载
- 空目录 / 无文件场景
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.knowledge.glossary import GlossaryManager


# ===========================================================================
# Helpers
# ===========================================================================

def _create_glossary_manager(glossary_dir: Path) -> GlossaryManager:
    """Create a GlossaryManager with a patched settings pointing to a temp dir."""
    mock_settings = MagicMock()
    mock_settings.corpus_glossary_dir = str(glossary_dir)
    with patch("app.knowledge.glossary.settings", mock_settings):
        mgr = GlossaryManager()
        mgr.reload()
    return mgr


def _write_json_glossary(dir_path: Path, terms=None, synonyms=None) -> Path:
    data = {}
    if terms:
        data["terms"] = terms
    if synonyms:
        data["synonyms"] = synonyms
    path = dir_path / "glossary.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _write_csv_glossary(dir_path: Path, rows: list[list[str]], header: str) -> Path:
    path = dir_path / "glossary.csv"
    lines = [header] + [",".join(row) for row in rows]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ===========================================================================
# JSON loading
# ===========================================================================

class TestJsonLoading:

    def test_load_terms(self, tmp_path):
        _write_json_glossary(tmp_path, terms=[
            {"term": "RSRP", "definition": "参考信号接收功率"},
            {"term": "SINR", "definition": "信号与干扰加噪声比"},
        ])
        mgr = _create_glossary_manager(tmp_path)
        assert len(mgr.terms) == 2
        assert mgr.terms["RSRP"] == "参考信号接收功率"
        assert mgr.terms["SINR"] == "信号与干扰加噪声比"

    def test_load_synonyms(self, tmp_path):
        _write_json_glossary(tmp_path, synonyms={
            "弱覆盖": ["覆盖不足", "信号弱"],
            "过覆盖": ["越区覆盖"],
        })
        mgr = _create_glossary_manager(tmp_path)
        assert len(mgr.synonyms) == 2
        assert "覆盖不足" in mgr.synonyms["弱覆盖"]
        assert "信号弱" in mgr.synonyms["弱覆盖"]

    def test_load_both(self, tmp_path):
        _write_json_glossary(
            tmp_path,
            terms=[{"term": "RSRP", "definition": "功率"}],
            synonyms={"弱覆盖": ["覆盖不足"]},
        )
        mgr = _create_glossary_manager(tmp_path)
        assert len(mgr.terms) == 1
        assert len(mgr.synonyms) == 1

    def test_empty_json(self, tmp_path):
        (tmp_path / "empty.json").write_text("{}", encoding="utf-8")
        mgr = _create_glossary_manager(tmp_path)
        assert len(mgr.terms) == 0
        assert len(mgr.synonyms) == 0


# ===========================================================================
# CSV loading
# ===========================================================================

class TestCsvLoading:

    def test_load_term_csv(self, tmp_path):
        _write_csv_glossary(tmp_path, [
            ["RSRP", "参考信号接收功率"],
            ["SINR", "信号与干扰加噪声比"],
        ], header="term,definition")
        mgr = _create_glossary_manager(tmp_path)
        assert len(mgr.terms) == 2
        assert mgr.terms["RSRP"] == "参考信号接收功率"

    def test_load_synonym_csv(self, tmp_path):
        _write_csv_glossary(tmp_path, [
            ["弱覆盖", "覆盖不足"],
            ["弱覆盖", "信号弱"],
            ["过覆盖", "越区覆盖"],
        ], header="canonical,alias")
        mgr = _create_glossary_manager(tmp_path)
        assert "弱覆盖" in mgr.synonyms
        assert len(mgr.synonyms["弱覆盖"]) == 2


# ===========================================================================
# expand_query
# ===========================================================================

class TestExpandQuery:

    def test_expand_alias_to_canonical(self, tmp_path):
        _write_json_glossary(tmp_path, synonyms={"弱覆盖": ["覆盖不足"]})
        mgr = _create_glossary_manager(tmp_path)
        result = mgr.expand_query("覆盖不足")
        assert "弱覆盖" in result

    def test_expand_canonical_to_aliases(self, tmp_path):
        _write_json_glossary(tmp_path, synonyms={"弱覆盖": ["覆盖不足", "信号弱"]})
        mgr = _create_glossary_manager(tmp_path)
        result = mgr.expand_query("弱覆盖")
        assert "覆盖不足" in result
        assert "信号弱" in result

    def test_no_expansion(self, tmp_path):
        _write_json_glossary(tmp_path, synonyms={"弱覆盖": ["覆盖不足"]})
        mgr = _create_glossary_manager(tmp_path)
        result = mgr.expand_query("其他问题")
        assert result == "其他问题"


# ===========================================================================
# find_matching_terms
# ===========================================================================

class TestFindMatchingTerms:

    def test_match_found(self, tmp_path):
        _write_json_glossary(tmp_path, terms=[
            {"term": "RSRP", "definition": "功率"},
            {"term": "SINR", "definition": "比值"},
        ])
        mgr = _create_glossary_manager(tmp_path)
        matches = mgr.find_matching_terms("请分析RSRP指标异常")
        assert "RSRP" in matches
        assert "SINR" not in matches

    def test_no_match(self, tmp_path):
        _write_json_glossary(tmp_path, terms=[{"term": "RSRP", "definition": "功率"}])
        mgr = _create_glossary_manager(tmp_path)
        matches = mgr.find_matching_terms("天气预报")
        assert matches == []

    def test_case_insensitive(self, tmp_path):
        _write_json_glossary(tmp_path, terms=[{"term": "rsrp", "definition": "功率"}])
        mgr = _create_glossary_manager(tmp_path)
        matches = mgr.find_matching_terms("RSRP指标")
        assert len(matches) == 1


# ===========================================================================
# reload
# ===========================================================================

class TestReload:

    def test_reload_clears_and_reloads(self, tmp_path):
        _write_json_glossary(tmp_path, terms=[{"term": "A", "definition": "a"}])
        mock_settings = MagicMock()
        mock_settings.corpus_glossary_dir = str(tmp_path)

        with patch("app.knowledge.glossary.settings", mock_settings):
            mgr = GlossaryManager()
            mgr.reload()
            assert len(mgr.terms) == 1

            # Remove the file and reload
            (tmp_path / "glossary.json").unlink()
            mgr.reload()
            assert len(mgr.terms) == 0

    def test_reload_empty_dir(self, tmp_path):
        mgr = _create_glossary_manager(tmp_path)
        assert len(mgr.terms) == 0
        assert len(mgr.synonyms) == 0

    def test_reload_nonexistent_dir(self):
        mock_settings = MagicMock()
        mock_settings.corpus_glossary_dir = "/nonexistent/path"
        with patch("app.knowledge.glossary.settings", mock_settings):
            mgr = GlossaryManager()
            mgr.reload()  # Should not raise
            assert len(mgr.terms) == 0
