"""POST /api/hitl/{execution_id}/decide — Human-in-the-Loop decision endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agent.core import get_agent, get_checkpointer
from app.models.schemas import HITLAction, HITLDecision

router = APIRouter()


@router.post("/hitl/{execution_id}/decide")
async def hitl_decide(execution_id: str, decision: HITLDecision):
    """Submit a HITL decision (approve / edit / reject).

    The execution_id is the thread_id (conversation_id) used when the
    agent was interrupted. The agent is resumed with the human decision
    pushed as a Command to resolve the interrupt.
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
    try:
        from langgraph.types import Command

        # Resume the agent with the human decision
        config = {"configurable": {"thread_id": execution_id}}
        agent.invoke(
            Command(resume={
                "decisions":human_response
            }),
            config=config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"status": "ok", "action": decision.action}
