"""Corpus build pipeline: source files → Markdown → chunks → FAISS index."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.documents import Document

from app.config import settings
from app.knowledge.chunker import chunk_markdown_file
from app.knowledge.parsers.docling_parser import DoclingParser, DOCLING_EXTENSIONS
from app.knowledge.parsers.excel_parser import ExcelParser, EXCEL_EXTENSIONS

logger = logging.getLogger(__name__)


@dataclass
class BuildResult:
    """Result of a corpus build operation."""
    total_files: int = 0
    parsed_files: int = 0
    failed_files: int = 0
    total_chunks: int = 0
    errors: list[str] = field(default_factory=list)


class CorpusPipeline:
    """Orchestrates the full corpus build pipeline.

    Steps:
    1. Scan source directory for supported files
    2. Parse each file to Markdown (via Docling or Pandas)
    3. Chunk the Markdown files
    4. Return chunks ready for embedding and FAISS indexing

    The pipeline uses a full-rebuild strategy: existing parsed Markdown
    and indexes are cleared before rebuilding.
    """

    def __init__(self) -> None:
        self.is_building = False
        self._docling_parser = DoclingParser(image_dir=settings.corpus_image_dir)
        self._excel_parser = ExcelParser()

    def build(self, on_progress=None) -> BuildResult:
        """Execute the full build pipeline.

        Args:
            on_progress: Optional callback(stage: str, current: int, total: int)
                for reporting progress.

        Returns:
            BuildResult with statistics.
        """
        if self.is_building:
            raise RuntimeError("Build already in progress")

        self.is_building = True
        result = BuildResult()

        try:
            source_dir = Path(settings.corpus_source_dir)
            md_dir = Path(settings.corpus_md_dir)

            if not source_dir.exists():
                logger.warning("Corpus source directory does not exist: %s", source_dir)
                source_dir.mkdir(parents=True, exist_ok=True)
                return result

            # Step 1: Clear existing parsed output (full rebuild)
            if md_dir.exists():
                # Preserve glossary directory
                glossary_dir = md_dir / "glossary"
                glossary_backup = None
                if glossary_dir.exists():
                    glossary_backup = md_dir.parent / "_glossary_backup"
                    if glossary_backup.exists():
                        shutil.rmtree(glossary_backup)
                    shutil.copytree(glossary_dir, glossary_backup)

                shutil.rmtree(md_dir)

                if glossary_backup and glossary_backup.exists():
                    md_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(glossary_backup, glossary_dir)
                    shutil.rmtree(glossary_backup)

            md_dir.mkdir(parents=True, exist_ok=True)

            # Step 2: Discover source files (excludes .md — handled in step 4)
            source_files = self._discover_files(source_dir)
            result.total_files = len(source_files)

            if on_progress and source_files:
                on_progress("parsing", 0, result.total_files)

            # Step 3: Parse each file
            parsed_md_files: list[Path] = []
            for i, src_file in enumerate(source_files):
                try:
                    md_files = self._parse_file(src_file, md_dir)
                    if md_files:
                        parsed_md_files.extend(md_files)
                        result.parsed_files += 1
                    else:
                        result.failed_files += 1
                        result.errors.append(f"Parse returned no output: {src_file.name}")
                except Exception as e:
                    result.failed_files += 1
                    result.errors.append(f"{src_file.name}: {e}")
                    logger.exception("Failed to parse %s", src_file.name)

                if on_progress:
                    on_progress("parsing", i + 1, result.total_files)

            # Step 4: Also include any pre-existing .md files from source dir
            for md_file in sorted(source_dir.glob("*.md")):
                dest = md_dir / md_file.name
                if not dest.exists():
                    shutil.copy2(md_file, dest)
                    parsed_md_files.append(dest)

            # Step 5: Chunk all Markdown files
            if on_progress:
                on_progress("chunking", 0, len(parsed_md_files))

            all_chunks: list[Document] = []
            for i, md_file in enumerate(parsed_md_files):
                chunks = chunk_markdown_file(md_file)
                all_chunks.extend(chunks)
                if on_progress:
                    on_progress("chunking", i + 1, len(parsed_md_files))

            result.total_chunks = len(all_chunks)
            logger.info(
                "Pipeline complete: %d files → %d parsed → %d chunks",
                result.total_files, result.parsed_files, result.total_chunks,
            )
            return result

        finally:
            self.is_building = False

    def get_chunks(self) -> list[Document]:
        """Load and chunk all existing Markdown files in corpus_md_dir.

        Used after build() to get chunks for indexing, or to re-index
        from already-parsed Markdown without re-parsing source files.
        """
        md_dir = Path(settings.corpus_md_dir)
        if not md_dir.exists():
            return []

        all_chunks: list[Document] = []
        for md_file in sorted(md_dir.glob("*.md")):
            chunks = chunk_markdown_file(md_file)
            all_chunks.extend(chunks)

        return all_chunks

    def _discover_files(self, source_dir: Path) -> list[Path]:
        """Find all supported files in the source directory."""
        supported = DOCLING_EXTENSIONS | EXCEL_EXTENSIONS | {".md"}
        files = []
        for f in sorted(source_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in supported and f.suffix.lower() != ".md":
                files.append(f)
        return files

    def _parse_file(self, file_path: Path, output_dir: Path) -> list[Path]:
        """Parse a single file into Markdown."""
        if DoclingParser.can_parse(file_path):
            result = self._docling_parser.parse(file_path, output_dir)
            return [result] if result else []
        elif ExcelParser.can_parse(file_path):
            return self._excel_parser.parse(file_path, output_dir)
        else:
            logger.warning("Unsupported file type: %s", file_path.suffix)
            return []


# Singleton
corpus_pipeline = CorpusPipeline()
