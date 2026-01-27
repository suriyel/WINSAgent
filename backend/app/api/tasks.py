"""GET /api/tasks/{task_id}/todos — TODO step listing."""

from __future__ import annotations

from fastapi import APIRouter

from app.agent.core import get_agent

router = APIRouter()


@router.get("/tasks/{task_id}/todos")
async def get_todos(task_id: str):
    """Retrieve TODO steps for a given task (thread_id).

    Reads from the agent's checkpointer state to get the latest todo list.
    """
    agent = get_agent()
    config = {"configurable": {"thread_id": task_id}}

    try:
        state = agent.get_state(config)
        todos = state.values.get("todos", [])
        return {
            "task_id": task_id,
            "steps": [
                {"content": t.get("content", ""), "status": t.get("status", "pending")}
                for t in todos
            ],
        }
    except Exception:
        return {"task_id": task_id, "steps": []}
