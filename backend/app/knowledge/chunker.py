"""Semantic chunker for Markdown documents.

Splits Markdown by heading structure to produce semantically coherent chunks,
preserving heading context as metadata for retrieval traceability.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.documents import Document


@dataclass
class ChunkMetadata:
    """Metadata attached to each chunk for retrieval traceability."""
    source_file: str
    heading_path: str          # e.g. "# Title > ## Section > ### Subsection"
    chunk_index: int
    content_hash: str
    has_images: bool = False
    image_refs: list[str] = field(default_factory=list)


def chunk_markdown_file(
    file_path: Path,
    *,
    max_chunk_size: int = 1200,
    min_chunk_size: int = 200,
    chunk_overlap: int = 100,
) -> list[Document]:
    """Split a Markdown file into semantically coherent chunks.

    Strategy:
    1. Split by heading hierarchy (##, ###, ####)
    2. Within each section, split by paragraph if section exceeds max_chunk_size
    3. Preserve heading path in metadata for traceability

    Args:
        file_path: Path to the Markdown file.
        max_chunk_size: Maximum characters per chunk.
        min_chunk_size: Minimum characters (smaller chunks merge with previous).
        chunk_overlap: Overlap characters between consecutive chunks in a section.

    Returns:
        List of LangChain Document objects with structured metadata.
    """
    text = file_path.read_text(encoding="utf-8")
    source_file = file_path.name
    content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

    sections = _split_by_headings(text)
    documents: list[Document] = []
    chunk_index = 0

    for heading_path, section_text in sections:
        if not section_text.strip():
            continue

        # Detect image references
        image_refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", section_text)

        # If section fits in one chunk, keep it whole
        if len(section_text) <= max_chunk_size:
            documents.append(Document(
                page_content=section_text.strip(),
                metadata={
                    "source_file": source_file,
                    "heading_path": heading_path,
                    "chunk_index": chunk_index,
                    "content_hash": content_hash,
                    "has_images": bool(image_refs),
                    "image_refs": image_refs,
                },
            ))
            chunk_index += 1
        else:
            # Split large sections by paragraph
            sub_chunks = _split_section(
                section_text,
                max_size=max_chunk_size,
                overlap=chunk_overlap,
            )
            for sub in sub_chunks:
                if len(sub.strip()) < min_chunk_size and documents:
                    # Merge tiny chunks with previous
                    prev = documents[-1]
                    documents[-1] = Document(
                        page_content=prev.page_content + "\n\n" + sub.strip(),
                        metadata=prev.metadata,
                    )
                    continue

                sub_image_refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", sub)
                documents.append(Document(
                    page_content=sub.strip(),
                    metadata={
                        "source_file": source_file,
                        "heading_path": heading_path,
                        "chunk_index": chunk_index,
                        "content_hash": content_hash,
                        "has_images": bool(sub_image_refs),
                        "image_refs": sub_image_refs,
                    },
                ))
                chunk_index += 1

    return documents


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """Split Markdown text into (heading_path, content) pairs.

    Returns a list of (heading_path, section_content) tuples where
    heading_path tracks the nesting like "# Title > ## Section".
    """
    # Match lines starting with # (heading levels 1-6)
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    sections: list[tuple[str, str]] = []
    heading_stack: list[tuple[int, str]] = []  # (level, title)
    last_pos = 0

    for match in heading_pattern.finditer(text):
        # Save content before this heading
        if last_pos < match.start():
            content = text[last_pos:match.start()]
            path = _build_heading_path(heading_stack)
            if content.strip():
                sections.append((path, content))

        level = len(match.group(1))
        title = match.group(2).strip()

        # Update heading stack
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, title))

        last_pos = match.start()

    # Remaining content after last heading
    if last_pos < len(text):
        content = text[last_pos:]
        path = _build_heading_path(heading_stack)
        if content.strip():
            sections.append((path, content))

    # If no headings found, return the whole text
    if not sections and text.strip():
        sections.append(("", text))

    return sections


def _build_heading_path(stack: list[tuple[int, str]]) -> str:
    """Build a heading path string like '# Title > ## Section > ### Sub'."""
    if not stack:
        return ""
    return " > ".join(f"{'#' * level} {title}" for level, title in stack)


def _split_section(text: str, max_size: int, overlap: int) -> list[str]:
    """Split a section into chunks by paragraph boundaries."""
    paragraphs = re.split(r"\n\n+", text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if not para.strip():
            continue

        if len(current) + len(para) + 2 <= max_size:
            current = current + "\n\n" + para if current else para
        else:
            if current:
                chunks.append(current)
                # Apply overlap: keep tail of current chunk
                if overlap > 0 and len(current) > overlap:
                    current = current[-overlap:] + "\n\n" + para
                else:
                    current = para
            else:
                # Single paragraph exceeds max_size — keep it whole
                chunks.append(para)
                current = ""

    if current:
        chunks.append(current)

    return chunks
