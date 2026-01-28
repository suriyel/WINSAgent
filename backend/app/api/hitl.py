"""POST /api/hitl/{execution_id}/decide — Human-in-the-Loop decision endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.core import get_agent
from app.models.schemas import HITLAction, HITLDecision
from app.sse.event_mapper import map_agent_stream_to_sse

router = APIRouter()


@router.post("/hitl/{execution_id}/decide")
async def hitl_decide(execution_id: str, decision: HITLDecision):
    """Submit a HITL decision (approve / edit / reject).

    The execution_id is the thread_id (conversation_id) used when the
    agent was interrupted. The agent is resumed with the human decision
    pushed as a Command to resolve the interrupt.

    Returns an SSE stream with tool results and agent response.
    """
    agent = get_agent()

    # Build the human response based on the decision
    decisions = []
    if decision.action == HITLAction.approve:
        human_response = {"type": "approve"}
    elif decision.action == HITLAction.edit:
        human_response = {"type": "edit",
                          "edited_action": {
                              "name": decision.tool_name,
                              "args": decision.edited_params
                          }}
    elif decision.action == HITLAction.reject:
        human_response = {"type": "reject"}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {decision.action}")

    decisions.append(human_response)

    from langgraph.types import Command

    # Resume the agent with the human decision using stream mode
    config = {"configurable": {"thread_id": execution_id}}
    stream = agent.stream(
        Command(resume={"decisions": decisions}),
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
