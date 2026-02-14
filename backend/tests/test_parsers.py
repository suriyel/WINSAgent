"""Tests for document parsers (Excel parser).

验证:
- Excel 文件 → Markdown 表格转换
- 多 Sheet 输出多文件
- 空 Sheet 跳过
- NaN 值处理
- 管道符转义

注: Docling parser 测试需要 docling 库安装，标记为 live。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas", reason="pandas not installed")

from app.knowledge.parsers.excel_parser import ExcelParser, _is_nan


# ===========================================================================
# ExcelParser
# ===========================================================================

class TestExcelParser:

    @pytest.fixture
    def parser(self):
        return ExcelParser()

    @pytest.fixture
    def sample_excel(self, tmp_path):
        """Create a minimal Excel file with pandas."""
        import pandas as pd
        data = {"Name": ["Alice", "Bob"], "Score": [95, 88]}
        df = pd.DataFrame(data)
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False, sheet_name="Sheet1")
        return path

    @pytest.fixture
    def multi_sheet_excel(self, tmp_path):
        """Create an Excel file with multiple sheets."""
        import pandas as pd
        path = tmp_path / "multi.xlsx"
        with pd.ExcelWriter(path) as writer:
            pd.DataFrame({"A": [1, 2]}).to_excel(writer, sheet_name="Data1", index=False)
            pd.DataFrame({"B": [3, 4]}).to_excel(writer, sheet_name="Data2", index=False)
        return path

    @pytest.fixture
    def empty_sheet_excel(self, tmp_path):
        """Create an Excel file with an empty sheet."""
        import pandas as pd
        path = tmp_path / "empty.xlsx"
        with pd.ExcelWriter(path) as writer:
            pd.DataFrame({"X": [1]}).to_excel(writer, sheet_name="HasData", index=False)
            pd.DataFrame().to_excel(writer, sheet_name="Empty", index=False)
        return path

    def test_can_parse(self):
        assert ExcelParser.can_parse(Path("file.xlsx"))
        assert ExcelParser.can_parse(Path("file.xls"))
        assert ExcelParser.can_parse(Path("file.xlsm"))
        assert not ExcelParser.can_parse(Path("file.csv"))
        assert not ExcelParser.can_parse(Path("file.pdf"))

    def test_parse_single_sheet(self, parser, sample_excel, tmp_path):
        results = parser.parse(sample_excel, tmp_path)
        assert len(results) == 1
        content = results[0].read_text(encoding="utf-8")
        assert "| Name | Score |" in content
        assert "| Alice | 95 |" in content
        assert "| Bob | 88 |" in content

    def test_parse_multi_sheet(self, parser, multi_sheet_excel, tmp_path):
        results = parser.parse(multi_sheet_excel, tmp_path)
        assert len(results) == 2
        names = [r.name for r in results]
        assert any("Data1" in n for n in names)
        assert any("Data2" in n for n in names)

    def test_empty_sheet_skipped(self, parser, empty_sheet_excel, tmp_path):
        results = parser.parse(empty_sheet_excel, tmp_path)
        # Only the non-empty sheet should produce output
        assert len(results) == 1

    def test_output_is_valid_markdown_table(self, parser, sample_excel, tmp_path):
        results = parser.parse(sample_excel, tmp_path)
        content = results[0].read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        # Should have: heading, blank line, header row, separator row, data rows
        table_lines = [l for l in lines if l.startswith("|")]
        assert len(table_lines) >= 3  # header + separator + at least 1 data row
        # Separator should be all ---
        assert all(c in "-| " for c in table_lines[1])

    def test_pipe_char_escaped(self, parser, tmp_path):
        """Pipe characters in cell values should be escaped."""
        import pandas as pd
        data = {"Col": ["a|b", "c"]}
        path = tmp_path / "pipe.xlsx"
        pd.DataFrame(data).to_excel(path, index=False)
        results = parser.parse(path, tmp_path)
        content = results[0].read_text(encoding="utf-8")
        assert "a\\|b" in content

    def test_nonexistent_file(self, parser, tmp_path):
        results = parser.parse(tmp_path / "nonexistent.xlsx", tmp_path)
        assert results == []


# ===========================================================================
# _is_nan helper
# ===========================================================================

class TestIsNan:

    def test_nan_float(self):
        assert _is_nan(float("nan"))

    def test_normal_float(self):
        assert not _is_nan(3.14)

    def test_string(self):
        assert not _is_nan("hello")

    def test_none(self):
        assert not _is_nan(None)

    def test_integer(self):
        assert not _is_nan(42)
