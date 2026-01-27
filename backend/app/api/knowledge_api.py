"""POST /api/knowledge/rebuild — Trigger knowledge base rebuild."""

from __future__ import annotations

from fastapi import APIRouter

from app.knowledge.vector_store import knowledge_manager
from app.models.schemas import RebuildKnowledgeRequest

router = APIRouter()


@router.post("/knowledge/rebuild", status_code=202)
async def rebuild_knowledge(request: RebuildKnowledgeRequest | None = None):
    """Force rebuild FAISS indexes from Markdown documents."""
    knowledge_type = request.knowledge_type if request else None
    counts = knowledge_manager.rebuild(knowledge_type)
    return {
        "status": "accepted",
        "rebuilt": counts,
    }
