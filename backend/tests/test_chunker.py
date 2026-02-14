"""Tests for semantic Markdown chunker.

验证:
- Heading 层级拆分
- 超长段落二次切分
- 小 chunk 合并
- 图片引用检测
- 元数据（heading_path, source_file, content_hash）正确性
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.knowledge.chunker import (
    chunk_markdown_file,
    _split_by_headings,
    _build_heading_path,
    _split_section,
)


# ===========================================================================
# _split_by_headings
# ===========================================================================

class TestSplitByHeadings:

    def test_single_section_no_headings(self):
        text = "This is plain text without any headings."
        sections = _split_by_headings(text)
        assert len(sections) == 1
        assert sections[0][0] == ""
        assert "plain text" in sections[0][1]

    def test_multiple_h2_sections(self):
        text = "# Title\n\nIntro text.\n\n## Section A\n\nContent A.\n\n## Section B\n\nContent B."
        sections = _split_by_headings(text)
        # Should produce sections for: Title+intro, Section A, Section B
        assert len(sections) >= 3
        # Check heading paths exist
        paths = [s[0] for s in sections]
        assert any("Section A" in p for p in paths)
        assert any("Section B" in p for p in paths)

    def test_nested_headings(self):
        text = "# Doc\n\n## Chapter 1\n\n### Section 1.1\n\nContent.\n\n## Chapter 2\n\nMore content."
        sections = _split_by_headings(text)
        paths = [s[0] for s in sections]
        # Section 1.1 should have nested path
        nested = [p for p in paths if "Section 1.1" in p]
        assert len(nested) == 1
        assert "Chapter 1" in nested[0]  # Parent heading should be in path

    def test_empty_text(self):
        sections = _split_by_headings("")
        assert sections == []


# ===========================================================================
# _build_heading_path
# ===========================================================================

class TestBuildHeadingPath:

    def test_empty_stack(self):
        assert _build_heading_path([]) == ""

    def test_single_level(self):
        result = _build_heading_path([(1, "Title")])
        assert result == "# Title"

    def test_nested_path(self):
        result = _build_heading_path([(1, "Doc"), (2, "Chapter"), (3, "Section")])
        assert result == "# Doc > ## Chapter > ### Section"


# ===========================================================================
# _split_section
# ===========================================================================

class TestSplitSection:

    def test_small_text_single_chunk(self):
        text = "Short paragraph."
        chunks = _split_section(text, max_size=100, overlap=10)
        assert len(chunks) == 1
        assert chunks[0] == "Short paragraph."

    def test_multiple_paragraphs_split(self):
        text = "Para one content here.\n\nPara two content here.\n\nPara three content here."
        chunks = _split_section(text, max_size=30, overlap=5)
        assert len(chunks) >= 2

    def test_single_oversized_paragraph(self):
        """A single paragraph exceeding max_size should be kept whole."""
        text = "A" * 200
        chunks = _split_section(text, max_size=50, overlap=10)
        assert len(chunks) == 1
        assert chunks[0] == text


# ===========================================================================
# chunk_markdown_file
# ===========================================================================

class TestChunkMarkdownFile:

    def _write_temp_md(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return Path(f.name)

    def test_basic_chunking(self):
        md = "# Title\n\nIntro paragraph.\n\n## Section\n\nSection content here."
        path = self._write_temp_md(md)
        try:
            chunks = chunk_markdown_file(path)
            assert len(chunks) >= 2
            # All chunks should have metadata
            for c in chunks:
                assert "source_file" in c.metadata
                assert "heading_path" in c.metadata
                assert "chunk_index" in c.metadata
                assert "content_hash" in c.metadata
                assert c.metadata["source_file"] == path.name
        finally:
            path.unlink()

    def test_image_ref_detection(self):
        md = "# Doc\n\nSome text.\n\n![diagram](images/abc123/fig1.png)\n\nMore text."
        path = self._write_temp_md(md)
        try:
            chunks = chunk_markdown_file(path)
            # At least one chunk should have images
            has_img = [c for c in chunks if c.metadata.get("has_images")]
            assert len(has_img) >= 1
            assert "images/abc123/fig1.png" in has_img[0].metadata["image_refs"]
        finally:
            path.unlink()

    def test_chunk_index_sequential(self):
        md = "# A\n\nText A.\n\n## B\n\nText B.\n\n## C\n\nText C."
        path = self._write_temp_md(md)
        try:
            chunks = chunk_markdown_file(path)
            indices = [c.metadata["chunk_index"] for c in chunks]
            assert indices == list(range(len(chunks)))
        finally:
            path.unlink()

    def test_content_hash_consistent(self):
        md = "# Title\n\nContent."
        path = self._write_temp_md(md)
        try:
            chunks1 = chunk_markdown_file(path)
            chunks2 = chunk_markdown_file(path)
            assert chunks1[0].metadata["content_hash"] == chunks2[0].metadata["content_hash"]
        finally:
            path.unlink()

    def test_large_section_splits(self):
        """A very large section should be split into multiple chunks."""
        large_text = "\n\n".join([f"Paragraph {i}: " + "x" * 200 for i in range(20)])
        md = f"# Title\n\n{large_text}"
        path = self._write_temp_md(md)
        try:
            chunks = chunk_markdown_file(path, max_chunk_size=500)
            assert len(chunks) > 1
        finally:
            path.unlink()

    def test_empty_file(self):
        path = self._write_temp_md("")
        try:
            chunks = chunk_markdown_file(path)
            assert chunks == []
        finally:
            path.unlink()
