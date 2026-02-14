"""Excel parser: converts Excel sheets to Standard Markdown Tables using Pandas."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}


class ExcelParser:
    """Parse Excel files into Markdown tables.

    Each sheet is converted to a separate Markdown file with a
    Standard Markdown Table preserving row/column relationships.
    """

    @staticmethod
    def can_parse(file_path: Path) -> bool:
        return file_path.suffix.lower() in EXCEL_EXTENSIONS

    def parse(self, file_path: Path, output_dir: Path) -> list[Path]:
        """Parse an Excel file into one or more Markdown files.

        Args:
            file_path: Path to the Excel file.
            output_dir: Directory to write the generated .md files.

        Returns:
            List of paths to generated Markdown files.
        """
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas is not installed. Run: pip install pandas openpyxl")
            return []

        output_paths: list[Path] = []

        try:
            xls = pd.ExcelFile(file_path, engine="openpyxl")
        except Exception:
            logger.exception("Failed to open Excel file: %s", file_path.name)
            return []

        for sheet_name in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet_name)

                if df.empty:
                    logger.debug("Skipping empty sheet: %s/%s", file_path.name, sheet_name)
                    continue

                md_content = self._dataframe_to_markdown(df, file_path.name, sheet_name)

                # Generate output filename
                safe_sheet = sheet_name.replace("/", "_").replace("\\", "_")
                if len(xls.sheet_names) == 1:
                    output_name = f"{file_path.stem}.md"
                else:
                    output_name = f"{file_path.stem}_{safe_sheet}.md"

                output_path = output_dir / output_name
                output_path.write_text(md_content, encoding="utf-8")
                output_paths.append(output_path)

                logger.info(
                    "Parsed %s [%s] → %s (%d rows)",
                    file_path.name, sheet_name, output_name, len(df),
                )
            except Exception:
                logger.exception(
                    "Failed to parse sheet %s in %s", sheet_name, file_path.name
                )

        return output_paths

    @staticmethod
    def _dataframe_to_markdown(df, source_file: str, sheet_name: str) -> str:
        """Convert a DataFrame to a Markdown document with metadata header."""
        lines: list[str] = []

        # Add metadata header
        lines.append(f"# {source_file} — {sheet_name}")
        lines.append("")

        # Convert to markdown table
        headers = list(df.columns)
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")

        for _, row in df.iterrows():
            cells = []
            for val in row:
                cell = str(val) if not _is_nan(val) else ""
                # Escape pipe characters in cell content
                cell = cell.replace("|", "\\|")
                cells.append(cell)
            lines.append("| " + " | ".join(cells) + " |")

        lines.append("")
        return "\n".join(lines)


def _is_nan(val) -> bool:
    """Check if a value is NaN (works for any type)."""
    try:
        import math
        return isinstance(val, float) and math.isnan(val)
    except (TypeError, ValueError):
        return False
