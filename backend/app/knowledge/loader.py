"""Markdown document loading and text splitting for FAISS indexing."""

from __future__ import annotations

import hashlib
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def compute_hash(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def load_markdown_directory(directory: str) -> list[Document]:
    """Load all .md files from *directory* and split into chunks."""
    docs: list[Document] = []
    dir_path = Path(directory)
    if not dir_path.exists():
        return docs

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " "],
    )

    for md_file in sorted(dir_path.glob("*.md")):
        raw_text = md_file.read_text(encoding="utf-8")
        chunks = splitter.split_text(raw_text)
        for i, chunk in enumerate(chunks):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source": md_file.name,
                        "chunk_index": i,
                        "content_hash": compute_hash(raw_text),
                    },
                )
            )
    return docs
