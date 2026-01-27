"""GET /api/conversations — Conversation listing and detail."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

router = APIRouter()

# In-memory store (validation stage)
_conversations: dict[str, dict] = {}


def _ensure_conversation(cid: str) -> dict:
    if cid not in _conversations:
        now = datetime.now(timezone.utc).isoformat()
        _conversations[cid] = {
            "id": cid,
            "title": f"会话 {cid[:8]}",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
    return _conversations[cid]


@router.get("/conversations")
async def list_conversations():
    return [
        {
            "id": c["id"],
            "title": c["title"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
        }
        for c in _conversations.values()
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    conv = _conversations.get(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
