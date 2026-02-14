"""Tests for corpus build pipeline.

验证:
- 文件发现逻辑
- Excel 文件解析集成
- 空目录处理
- 构建状态标志 (is_building)
- get_chunks 从已解析 MD 加载
- 错误文件跳过不中断
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# ===========================================================================
# Helpers
# ===========================================================================

def _make_pipeline(source_dir: Path, md_dir: Path):
    """Create a CorpusPipeline with mocked settings."""
    mock_settings = MagicMock()
    mock_settings.corpus_source_dir = str(source_dir)
    mock_settings.corpus_md_dir = str(md_dir)
    mock_settings.corpus_image_dir = str(md_dir / "images")
    mock_settings.corpus_glossary_dir = str(md_dir / "glossary")

    with patch("app.knowledge.pipeline.settings", mock_settings):
        from app.knowledge.pipeline import CorpusPipeline
        pipeline = CorpusPipeline()
    return pipeline, mock_settings


# ===========================================================================
# File discovery
# ===========================================================================

class TestFileDiscovery:

    def test_discover_supported_files(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "doc.pdf").touch()
        (source / "data.xlsx").touch()
        (source / "notes.md").touch()   # .md should be excluded from parsing
        (source / "readme.txt").touch()  # .txt not supported

        pipeline, _ = _make_pipeline(source, tmp_path / "md")
        files = pipeline._discover_files(source)
        names = {f.name for f in files}
        assert "doc.pdf" in names
        assert "data.xlsx" in names
        assert "notes.md" not in names   # .md handled separately
        assert "readme.txt" not in names

    def test_empty_directory(self, tmp_path):
        source = tmp_path / "empty_source"
        source.mkdir()
        pipeline, _ = _make_pipeline(source, tmp_path / "md")
        files = pipeline._discover_files(source)
        assert files == []


# ===========================================================================
# Build pipeline
# ===========================================================================

class TestBuild:

    @pytest.mark.skipif(not HAS_PANDAS, reason="pandas not installed")
    def test_build_with_excel_file(self, tmp_path):
        import pandas as pd

        source = tmp_path / "source"
        source.mkdir()
        md_dir = tmp_path / "md"

        # Create a test Excel file
        df = pd.DataFrame({"Name": ["Alice", "Bob"], "Score": [95, 88]})
        df.to_excel(source / "test.xlsx", index=False)

        pipeline, mock_settings = _make_pipeline(source, md_dir)

        with patch("app.knowledge.pipeline.settings", mock_settings):
            result = pipeline.build()

        assert result.total_files == 1
        assert result.parsed_files == 1
        assert result.failed_files == 0
        assert result.total_chunks > 0

    def test_build_with_existing_md(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        md_dir = tmp_path / "md"

        # Place an .md file directly in source
        md_content = "# Test Document\n\nSome content here.\n\n## Section\n\nMore content."
        (source / "existing.md").write_text(md_content, encoding="utf-8")

        pipeline, mock_settings = _make_pipeline(source, md_dir)

        with patch("app.knowledge.pipeline.settings", mock_settings):
            result = pipeline.build()

        # .md files are copied (not "parsed"), so total_files=0 but chunks exist
        assert result.total_files == 0  # _discover_files excludes .md
        # The MD should have been copied to md_dir and chunked
        assert (md_dir / "existing.md").exists()
        # Verify chunks via get_chunks
        with patch("app.knowledge.pipeline.settings", mock_settings):
            chunks = pipeline.get_chunks()
        assert len(chunks) > 0

    def test_build_empty_source(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        md_dir = tmp_path / "md"

        pipeline, mock_settings = _make_pipeline(source, md_dir)

        with patch("app.knowledge.pipeline.settings", mock_settings):
            result = pipeline.build()

        assert result.total_files == 0
        assert result.total_chunks == 0

    def test_build_nonexistent_source(self, tmp_path):
        source = tmp_path / "nonexistent"
        md_dir = tmp_path / "md"

        pipeline, mock_settings = _make_pipeline(source, md_dir)

        with patch("app.knowledge.pipeline.settings", mock_settings):
            result = pipeline.build()

        assert result.total_files == 0

    def test_is_building_flag(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        md_dir = tmp_path / "md"

        pipeline, mock_settings = _make_pipeline(source, md_dir)

        assert pipeline.is_building is False

        with patch("app.knowledge.pipeline.settings", mock_settings):
            # After build, flag should be reset
            pipeline.build()

        assert pipeline.is_building is False

    def test_concurrent_build_raises(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        md_dir = tmp_path / "md"

        pipeline, mock_settings = _make_pipeline(source, md_dir)
        pipeline.is_building = True

        with pytest.raises(RuntimeError, match="Build already in progress"):
            with patch("app.knowledge.pipeline.settings", mock_settings):
                pipeline.build()

    @pytest.mark.skipif(not HAS_PANDAS, reason="pandas not installed")
    def test_progress_callback(self, tmp_path):
        import pandas as pd

        source = tmp_path / "source"
        source.mkdir()
        md_dir = tmp_path / "md"

        df = pd.DataFrame({"A": [1]})
        df.to_excel(source / "small.xlsx", index=False)

        pipeline, mock_settings = _make_pipeline(source, md_dir)
        progress_calls = []

        with patch("app.knowledge.pipeline.settings", mock_settings):
            result = pipeline.build(on_progress=lambda stage, cur, total: progress_calls.append((stage, cur, total)))

        assert len(progress_calls) > 0
        stages = {c[0] for c in progress_calls}
        assert "parsing" in stages
        assert "chunking" in stages


# ===========================================================================
# get_chunks
# ===========================================================================

class TestGetChunks:

    def test_get_chunks_from_existing_md(self, tmp_path):
        md_dir = tmp_path / "md"
        md_dir.mkdir()

        (md_dir / "doc.md").write_text(
            "# Title\n\nContent.\n\n## Section\n\nMore content.",
            encoding="utf-8",
        )

        pipeline, mock_settings = _make_pipeline(tmp_path / "source", md_dir)

        with patch("app.knowledge.pipeline.settings", mock_settings):
            chunks = pipeline.get_chunks()

        assert len(chunks) >= 2
        assert all(c.metadata["source_file"] == "doc.md" for c in chunks)

    def test_get_chunks_empty_dir(self, tmp_path):
        md_dir = tmp_path / "md"
        md_dir.mkdir()

        pipeline, mock_settings = _make_pipeline(tmp_path / "source", md_dir)

        with patch("app.knowledge.pipeline.settings", mock_settings):
            chunks = pipeline.get_chunks()

        assert chunks == []

    def test_get_chunks_nonexistent_dir(self, tmp_path):
        pipeline, mock_settings = _make_pipeline(tmp_path / "source", tmp_path / "nonexistent")

        with patch("app.knowledge.pipeline.settings", mock_settings):
            chunks = pipeline.get_chunks()

        assert chunks == []
