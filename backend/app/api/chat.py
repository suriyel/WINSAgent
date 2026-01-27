"""POST /api/chat — SSE streaming endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.core import get_agent
from app.models.schemas import ChatRequest
from app.sse.event_mapper import map_agent_stream_to_sse

router = APIRouter()

# In-memory conversation store (validation stage)
_conversations: dict[str, list[dict]] = {}


@router.post("/chat")
async def chat(request: ChatRequest):
    """Start or continue a conversation. Returns an SSE event stream."""
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Retrieve or init conversation message history
    if conversation_id not in _conversations:
        _conversations[conversation_id] = []

    _conversations[conversation_id].append({
        "role": "user",
        "content": request.message,
    })

    agent = get_agent()

    config = {"configurable": {"thread_id": conversation_id}}

    stream = agent.stream(
        {"messages": [{"role": "user", "content": request.message}]},
        config=config,
        stream_mode="updates",
    )

    async def generate():
        # Emit conversation_id as first event
        import json
        yield f"event: session\ndata: {json.dumps({'conversation_id': conversation_id})}\n\n"

        async for sse_frame in map_agent_stream_to_sse(stream, conversation_id):
            yield sse_frame

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
