"""Corpus management API — build pipeline, file preview, glossary management."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.config import settings
from app.knowledge.pipeline import corpus_pipeline
from app.knowledge.vector_store import knowledge_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/corpus", tags=["corpus"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BuildResponse(BaseModel):
    status: str
    total_files: int
    parsed_files: int
    failed_files: int
    total_chunks: int
    indexed_chunks: int
    errors: list[str]


class CorpusFileInfo(BaseModel):
    file_id: str
    filename: str
    size_bytes: int


class CorpusFileContent(BaseModel):
    file_id: str
    filename: str
    chunks: list[dict[str, Any]]
    total_chunks: int
    offset: int
    limit: int


class CorpusFileMeta(BaseModel):
    file_id: str
    filename: str
    size_bytes: int
    total_chunks: int
    headings: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------

@router.post("/build", status_code=202, response_model=BuildResponse)
async def build_corpus():
    """Trigger full corpus build: parse source files → chunk → index.

    This is a blocking operation. For production use, consider running
    in a background task with progress reporting.
    """
    if corpus_pipeline.is_building:
        raise HTTPException(status_code=409, detail="Build already in progress")

    # Step 1: Parse and chunk
    result = corpus_pipeline.build()

    # Step 2: Index chunks
    chunks = corpus_pipeline.get_chunks()
    indexed = knowledge_manager.rebuild_corpus(chunks)

    return BuildResponse(
        status="completed",
        total_files=result.total_files,
        parsed_files=result.parsed_files,
        failed_files=result.failed_files,
        total_chunks=result.total_chunks,
        indexed_chunks=indexed,
        errors=result.errors,
    )


@router.get("/status")
async def corpus_status():
    """Check corpus build status and index statistics."""
    corpus_store = knowledge_manager.corpus_store
    return {
        "is_building": corpus_pipeline.is_building,
        "index_loaded": corpus_store is not None,
        "indexed_chunks": corpus_store.index.ntotal if corpus_store else 0,
    }


# ---------------------------------------------------------------------------
# File preview (M3)
# ---------------------------------------------------------------------------

@router.get("/files", response_model=list[CorpusFileInfo])
async def list_corpus_files():
    """List all parsed Markdown files in the corpus."""
    md_dir = Path(settings.corpus_md_dir)
    if not md_dir.exists():
        return []

    files = []
    for md_file in sorted(md_dir.glob("*.md")):
        file_id = hashlib.md5(md_file.name.encode()).hexdigest()[:12]
        files.append(CorpusFileInfo(
            file_id=file_id,
            filename=md_file.name,
            size_bytes=md_file.stat().st_size,
        ))
    return files


@router.get("/files/{file_id}", response_model=CorpusFileContent)
async def get_corpus_file(file_id: str, offset: int = 0, limit: int = 50, anchor: str | None = None):
    """Get paginated chunks of a corpus Markdown file.

    Args:
        file_id: MD5 hash prefix of the filename.
        offset: Chunk offset for pagination.
        limit: Number of chunks to return.
        anchor: Optional chunk_id to center the response around.
    """
    md_file = _resolve_file(file_id)
    if not md_file:
        raise HTTPException(status_code=404, detail="File not found")

    from app.knowledge.chunker import chunk_markdown_file
    chunks = chunk_markdown_file(md_file)

    # If anchor is specified, find the chunk and adjust offset
    if anchor is not None:
        for i, chunk in enumerate(chunks):
            if str(chunk.metadata.get("chunk_index")) == anchor:
                offset = max(0, i - limit // 2)
                break

    total = len(chunks)
    page = chunks[offset:offset + limit]

    return CorpusFileContent(
        file_id=file_id,
        filename=md_file.name,
        chunks=[
            {
                "chunk_index": c.metadata.get("chunk_index", i),
                "heading_path": c.metadata.get("heading_path", ""),
                "content": c.page_content,
                "has_images": c.metadata.get("has_images", False),
                "image_refs": c.metadata.get("image_refs", []),
            }
            for i, c in enumerate(page, start=offset)
        ],
        total_chunks=total,
        offset=offset,
        limit=limit,
    )


@router.get("/files/{file_id}/meta", response_model=CorpusFileMeta)
async def get_corpus_file_meta(file_id: str):
    """Get metadata for a corpus file including heading structure."""
    md_file = _resolve_file(file_id)
    if not md_file:
        raise HTTPException(status_code=404, detail="File not found")

    from app.knowledge.chunker import chunk_markdown_file
    chunks = chunk_markdown_file(md_file)

    # Extract unique headings for navigation
    seen_headings: set[str] = set()
    headings: list[dict[str, Any]] = []
    for chunk in chunks:
        hp = chunk.metadata.get("heading_path", "")
        if hp and hp not in seen_headings:
            seen_headings.add(hp)
            headings.append({
                "heading_path": hp,
                "chunk_index": chunk.metadata.get("chunk_index", 0),
            })

    return CorpusFileMeta(
        file_id=file_id,
        filename=md_file.name,
        size_bytes=md_file.stat().st_size,
        total_chunks=len(chunks),
        headings=headings,
    )


# ---------------------------------------------------------------------------
# Glossary management (M5)
# ---------------------------------------------------------------------------

@router.post("/glossary/upload")
async def upload_glossary(file: UploadFile = File(...)):
    """Upload a glossary file (JSON or CSV) for expert terminology management."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".json", ".csv"):
        raise HTTPException(status_code=400, detail="Only JSON and CSV files are supported")

    glossary_dir = Path(settings.corpus_glossary_dir)
    glossary_dir.mkdir(parents=True, exist_ok=True)

    dest = glossary_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    # Reload glossary manager if available
    try:
        from app.knowledge.glossary import glossary_manager
        glossary_manager.reload()
    except ImportError:
        pass

    return {"status": "uploaded", "filename": file.filename, "size_bytes": len(content)}


@router.get("/glossary")
async def list_glossary():
    """List uploaded glossary files and their content summary."""
    glossary_dir = Path(settings.corpus_glossary_dir)
    if not glossary_dir.exists():
        return {"files": [], "total_terms": 0}

    try:
        from app.knowledge.glossary import glossary_manager
        return {
            "files": [f.name for f in sorted(glossary_dir.iterdir()) if f.is_file()],
            "total_terms": len(glossary_manager.terms),
            "total_synonyms": len(glossary_manager.synonyms),
        }
    except ImportError:
        return {
            "files": [f.name for f in sorted(glossary_dir.iterdir()) if f.is_file()],
            "total_terms": 0,
        }


@router.delete("/glossary/{filename}")
async def delete_glossary_file(filename: str):
    """Delete a glossary file."""
    glossary_dir = Path(settings.corpus_glossary_dir)
    target = glossary_dir / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="Glossary file not found")

    target.unlink()

    # Reload glossary manager
    try:
        from app.knowledge.glossary import glossary_manager
        glossary_manager.reload()
    except ImportError:
        pass

    return {"status": "deleted", "filename": filename}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_file(file_id: str) -> Path | None:
    """Resolve a file_id to a Path in corpus_md_dir."""
    md_dir = Path(settings.corpus_md_dir)
    if not md_dir.exists():
        return None

    for md_file in md_dir.glob("*.md"):
        fid = hashlib.md5(md_file.name.encode()).hexdigest()[:12]
        if fid == file_id:
            return md_file
    return None
