"""Docling-based parser for Word/PDF/PPT → Markdown conversion with image extraction."""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Supported file extensions for Docling
DOCLING_EXTENSIONS = {".pdf", ".docx", ".doc", ".pptx", ".ppt"}


class DoclingParser:
    """Parse Word/PDF/PPT documents into Markdown using Docling engine.

    Extracts images and saves them alongside the generated Markdown,
    preserving image placeholders in the output.
    """

    def __init__(self, image_dir: str) -> None:
        self.image_dir = Path(image_dir)
        self.image_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def can_parse(file_path: Path) -> bool:
        return file_path.suffix.lower() in DOCLING_EXTENSIONS

    def parse(self, file_path: Path, output_dir: Path) -> Path | None:
        """Parse a document file into Markdown.

        Args:
            file_path: Path to the source document.
            output_dir: Directory to write the generated .md file.

        Returns:
            Path to the generated Markdown file, or None on failure.
        """
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            logger.error("docling is not installed. Run: pip install docling")
            return None

        file_hash = hashlib.md5(file_path.name.encode()).hexdigest()[:12]
        img_subdir = self.image_dir / file_hash
        img_subdir.mkdir(parents=True, exist_ok=True)

        try:
            converter = DocumentConverter()
            result = converter.convert(str(file_path))

            md_content = result.document.export_to_markdown(
                image_mode="referenced",
            )

            # Move any extracted images to our image directory
            self._relocate_images(result, img_subdir, file_hash)

            # Rewrite image paths in markdown to use our image directory
            md_content = self._rewrite_image_paths(md_content, file_hash)

            # Write markdown output
            output_path = output_dir / f"{file_path.stem}.md"
            output_path.write_text(md_content, encoding="utf-8")

            logger.info("Parsed %s → %s (%d chars)", file_path.name, output_path.name, len(md_content))
            return output_path

        except Exception:
            logger.exception("Failed to parse %s", file_path.name)
            return None

    def _relocate_images(self, result, img_subdir: Path, file_hash: str) -> None:
        """Move extracted images from Docling output to our image directory."""
        try:
            for element in result.document.iterate_items():
                if hasattr(element, "image") and element.image:
                    img_data = element.image
                    if hasattr(img_data, "pil_image") and img_data.pil_image:
                        img_name = f"img_{id(element)}.png"
                        img_path = img_subdir / img_name
                        img_data.pil_image.save(str(img_path))
        except Exception:
            logger.debug("Image extraction skipped for %s", file_hash)

    @staticmethod
    def _rewrite_image_paths(md_content: str, file_hash: str) -> str:
        """Rewrite image references to point to our image directory."""
        import re
        # Replace relative image paths with our corpus image path
        def _replace(match):
            alt = match.group(1)
            original_path = match.group(2)
            filename = Path(original_path).name
            return f"![{alt}](images/{file_hash}/{filename})"

        return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _replace, md_content)
