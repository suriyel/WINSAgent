"""POST /api/params/{execution_id}/decide — Missing-params decision endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.core import get_agent
from app.models.schemas import ParamsDecision
from app.sse.event_mapper import map_agent_stream_to_sse

router = APIRouter()


@router.post("/params/{execution_id}/decide")
async def params_decide(execution_id: str, decision: ParamsDecision):
    """Submit a missing-params decision (submit / cancel).

    The execution_id is the thread_id (conversation_id) used when the
    agent was interrupted by MissingParamsMiddleware.  The agent is
    resumed with the user-supplied parameter values.

    Returns an SSE stream with subsequent tool results and agent response.
    """
    agent = get_agent()

    if decision.action.value not in ("submit", "cancel"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown params action: {decision.action}",
        )

    # MissingParamsMiddleware expects: {"action": "submit"|"cancel", "params": {...}}
    resume_value = {
        "action": decision.action.value,
        "params": decision.params,
    }

    from langgraph.types import Command

    config = {"configurable": {"thread_id": execution_id}}
    stream = agent.stream(
        Command(resume=resume_value),
        config=config,
        stream_mode="updates",
    )

    async def generate():
        async for sse_frame in map_agent_stream_to_sse(stream, execution_id):
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
