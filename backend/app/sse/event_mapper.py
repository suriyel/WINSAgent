"""Map agent.stream() output to structured SSE events."""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage


def _sse(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE frame."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


async def map_agent_stream_to_sse(
    stream,
    thread_id: str,
) -> AsyncIterator[str]:
    """Consume an agent stream and yield SSE-formatted strings.

    Event types emitted:
      - thinking      : LLM token-level output
      - tool.call     : Agent decided to call a tool
      - tool.result   : Tool returned a result
      - todo.state    : TODO list state updated
      - hitl.pending  : Human-in-the-Loop approval required
      - suggestions   : Quick reply suggestions (from SuggestionsMiddleware)
      - message       : Final assistant message
      - error         : Error occurred
    """

    try:
        for event in stream:
            # --- agent event dict structure varies by LangGraph version ---
            # Common shapes:
            #   {"agent": {"messages": [AIMessage(...)]}}
            #   {"tools": {"messages": [ToolMessage(...)]}}
            #   {"__interrupt__": [...]}

            # Handle interrupt (HITL)
            if "__interrupt__" in event:
                interrupts = event["__interrupt__"]
                for intr in interrupts:
                    value = intr.value if hasattr(intr, "value") else intr
                    if "action_requests" in value and "review_configs" in value:
                        action_requests = value["action_requests"]
                        review_configs = value["review_configs"]
                        for i, action_request in enumerate(action_requests):
                            review_config = review_configs[i]
                            yield _sse("hitl.pending", {
                                "execution_id": str(uuid.uuid4()),
                                "tool_name": action_request.get("name", "unknown") if isinstance(value, dict) else "unknown",
                                "params": action_request.get("args", {}) if isinstance(value, dict) else {},
                                "schema": review_config.get("allowed_decisions", {}) if isinstance(value, dict) else {},
                                "description": action_request.get("description", "") if isinstance(value, dict) else str(value),
                            })
                continue

            # Extract messages from the event
            messages = None
            node_name = None
            for key, val in event.items():
                if key.startswith("__"):
                    continue
                if isinstance(val, dict) and "messages" in val:
                    messages = val["messages"]
                    node_name = key
                    break

            if not messages:
                continue

            for msg in messages:
                # --- AI Message (model output) ---
                if isinstance(msg, (AIMessage, AIMessageChunk)):
                    # Tool calls
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            yield _sse("tool.call", {
                                "tool_name": tc.get("name", ""),
                                "params": tc.get("args", {}),
                                "execution_id": tc.get("id", str(uuid.uuid4())),
                            })
                    # Text content (thinking / final message)
                    if msg.content:
                        content = msg.content if isinstance(msg.content, str) else str(msg.content)
                        if content.strip():
                            # If there are no tool calls, this is likely a final message
                            if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                                yield _sse("message", {"content": content})
                            else:
                                yield _sse("thinking", {"token": content})

                # --- Tool Message (tool result) ---
                elif isinstance(msg, ToolMessage):
                    status = "failed" if getattr(msg, "status", None) == "error" else "success"
                    yield _sse("tool.result", {
                        "execution_id": getattr(msg, "tool_call_id", str(uuid.uuid4())),
                        "result": msg.content if isinstance(msg.content, str) else str(msg.content),
                        "status": status,
                    })

            # --- Check for state updates in the event values ---
            for key, val in event.items():
                if not isinstance(val, dict):
                    continue

                # TODO state updates
                if "todos" in val:
                    todos = val["todos"]
                    yield _sse("todo.state", {
                        "task_id": thread_id,
                        "steps": [
                            {"content": t.get("content", ""), "status": t.get("status", "pending")}
                            for t in todos
                        ] if isinstance(todos, list) else [],
                    })

                # Suggestions state updates (from SuggestionsMiddleware)
                if "suggestions" in val and val["suggestions"] is not None:
                    suggestions_data = val["suggestions"]
                    # Handle both Pydantic model and dict
                    if hasattr(suggestions_data, "model_dump"):
                        suggestions_data = suggestions_data.model_dump()
                    yield _sse("suggestions", {
                        "suggestions": suggestions_data.get("suggestions", []),
                        "multi_select": suggestions_data.get("multi_select", False),
                        "prompt": suggestions_data.get("prompt"),
                    })

    except Exception as exc:
        yield _sse("error", {
            "code": "AGENT_ERROR",
            "message": str(exc),
        })
