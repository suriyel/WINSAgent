"""Tests for corpus management API routes.

验证:
- POST /api/corpus/build — 触发构建
- GET /api/corpus/status — 状态查询
- GET /api/corpus/files — 文件列表
- GET /api/corpus/files/{id} — 分页 chunk 返回
- GET /api/corpus/files/{id}/meta — 文件元信息
- POST /api/corpus/glossary/upload — 上传词表
- GET /api/corpus/glossary — 词表列表
- DELETE /api/corpus/glossary/{filename} — 删除词表
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def corpus_md_dir(tmp_path):
    """Create a temp corpus_md dir with sample files."""
    md_dir = tmp_path / "corpus_md"
    md_dir.mkdir()
    glossary_dir = md_dir / "glossary"
    glossary_dir.mkdir()

    # Write a sample MD file
    (md_dir / "sample.md").write_text(
        "# Sample Doc\n\nIntro text.\n\n## Section 1\n\nContent of section 1.\n\n## Section 2\n\nContent of section 2.",
        encoding="utf-8",
    )
    return md_dir


@pytest.fixture
def patch_corpus_settings(corpus_md_dir):
    """Patch settings to use temp corpus dirs."""
    mock = MagicMock()
    mock.corpus_md_dir = str(corpus_md_dir)
    mock.corpus_image_dir = str(corpus_md_dir / "images")
    mock.corpus_glossary_dir = str(corpus_md_dir / "glossary")
    mock.corpus_source_dir = str(corpus_md_dir.parent / "source")
    mock.faiss_index_dir = str(corpus_md_dir.parent / "faiss")
    mock.reranker_base_url = ""
    mock.reranker_threshold = 0.3
    return mock


# ===========================================================================
# GET /api/corpus/status
# ===========================================================================

class TestCorpusStatus:

    def test_status_endpoint(self, client, patch_corpus_settings):
        with patch("app.api.corpus_api.corpus_pipeline") as mock_pipeline, \
             patch("app.api.corpus_api.knowledge_manager") as mock_km:
            mock_pipeline.is_building = False
            mock_km.corpus_store = None
            res = client.get("/api/corpus/status")

        assert res.status_code == 200
        data = res.json()
        assert "is_building" in data
        assert "index_loaded" in data
        assert data["is_building"] is False
        assert data["index_loaded"] is False


# ===========================================================================
# GET /api/corpus/files
# ===========================================================================

class TestListFiles:

    def test_list_files(self, client, corpus_md_dir, patch_corpus_settings):
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.get("/api/corpus/files")

        assert res.status_code == 200
        files = res.json()
        assert len(files) == 1
        assert files[0]["filename"] == "sample.md"
        assert files[0]["file_id"] == hashlib.md5(b"sample.md").hexdigest()[:12]

    def test_list_files_empty(self, client, tmp_path, patch_corpus_settings):
        empty_dir = tmp_path / "empty_md"
        empty_dir.mkdir()
        patch_corpus_settings.corpus_md_dir = str(empty_dir)
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.get("/api/corpus/files")

        assert res.status_code == 200
        assert res.json() == []


# ===========================================================================
# GET /api/corpus/files/{file_id}
# ===========================================================================

class TestGetFile:

    def test_get_file_chunks(self, client, corpus_md_dir, patch_corpus_settings):
        file_id = hashlib.md5(b"sample.md").hexdigest()[:12]
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.get(f"/api/corpus/files/{file_id}")

        assert res.status_code == 200
        data = res.json()
        assert data["filename"] == "sample.md"
        assert len(data["chunks"]) > 0
        assert data["total_chunks"] > 0

    def test_get_file_with_pagination(self, client, corpus_md_dir, patch_corpus_settings):
        file_id = hashlib.md5(b"sample.md").hexdigest()[:12]
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.get(f"/api/corpus/files/{file_id}?offset=0&limit=1")

        assert res.status_code == 200
        data = res.json()
        assert len(data["chunks"]) == 1

    def test_get_file_not_found(self, client, corpus_md_dir, patch_corpus_settings):
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.get("/api/corpus/files/nonexistent")

        assert res.status_code == 404


# ===========================================================================
# GET /api/corpus/files/{file_id}/meta
# ===========================================================================

class TestGetFileMeta:

    def test_get_meta(self, client, corpus_md_dir, patch_corpus_settings):
        file_id = hashlib.md5(b"sample.md").hexdigest()[:12]
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.get(f"/api/corpus/files/{file_id}/meta")

        assert res.status_code == 200
        data = res.json()
        assert data["filename"] == "sample.md"
        assert data["total_chunks"] > 0
        assert isinstance(data["headings"], list)

    def test_meta_not_found(self, client, corpus_md_dir, patch_corpus_settings):
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.get("/api/corpus/files/nonexistent/meta")

        assert res.status_code == 404


# ===========================================================================
# Glossary upload / list / delete
# ===========================================================================

class TestGlossary:

    def test_upload_json(self, client, corpus_md_dir, patch_corpus_settings):
        glossary_data = json.dumps({"terms": [{"term": "RSRP", "definition": "功率"}]})
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.post(
                "/api/corpus/glossary/upload",
                files={"file": ("terms.json", glossary_data.encode(), "application/json")},
            )

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "uploaded"
        assert data["filename"] == "terms.json"
        # File should exist on disk
        assert (corpus_md_dir / "glossary" / "terms.json").exists()

    def test_upload_csv(self, client, corpus_md_dir, patch_corpus_settings):
        csv_content = "term,definition\nRSRP,功率"
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.post(
                "/api/corpus/glossary/upload",
                files={"file": ("terms.csv", csv_content.encode(), "text/csv")},
            )

        assert res.status_code == 200

    def test_upload_unsupported_format(self, client, corpus_md_dir, patch_corpus_settings):
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.post(
                "/api/corpus/glossary/upload",
                files={"file": ("terms.txt", b"hello", "text/plain")},
            )

        assert res.status_code == 400

    def test_list_glossary(self, client, corpus_md_dir, patch_corpus_settings):
        # Write a glossary file first
        (corpus_md_dir / "glossary" / "test.json").write_text("{}", encoding="utf-8")

        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.get("/api/corpus/glossary")

        assert res.status_code == 200
        data = res.json()
        assert "test.json" in data["files"]

    def test_delete_glossary(self, client, corpus_md_dir, patch_corpus_settings):
        (corpus_md_dir / "glossary" / "to_delete.json").write_text("{}", encoding="utf-8")

        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.delete("/api/corpus/glossary/to_delete.json")

        assert res.status_code == 200
        assert not (corpus_md_dir / "glossary" / "to_delete.json").exists()

    def test_delete_nonexistent(self, client, corpus_md_dir, patch_corpus_settings):
        with patch("app.api.corpus_api.settings", patch_corpus_settings):
            res = client.delete("/api/corpus/glossary/nonexistent.json")

        assert res.status_code == 404
