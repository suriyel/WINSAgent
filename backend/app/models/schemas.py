"""Pydantic models for API request / response payloads."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TodoStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class HITLAction(str, Enum):
    approve = "approve"
    edit = "edit"
    reject = "reject"


class ToolCategory(str, Enum):
    query = "query"
    mutation = "mutation"
    long_running = "long_running"
    external = "external"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


class HITLDecision(BaseModel):
    action: HITLAction
    edited_params: dict[str, Any] = Field(default_factory=dict)


class RebuildKnowledgeRequest(BaseModel):
    knowledge_type: str | None = None  # "terminology" | "design_doc" | None (both)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TodoStepResponse(BaseModel):
    content: str
    status: TodoStatus


class TaskResponse(BaseModel):
    id: str
    conversation_id: str
    status: TaskStatus
    description: str
    created_at: datetime


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(BaseModel):
    id: str
    title: str
    messages: list[MessageResponse]


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    created_at: datetime


class ToolDefinitionResponse(BaseModel):
    name: str
    description: str
    parameters_schema: dict[str, Any]
    category: str
    requires_hitl: bool


# ---------------------------------------------------------------------------
# SSE Event payloads
# ---------------------------------------------------------------------------

class SSEThinkingEvent(BaseModel):
    token: str


class SSEToolCallEvent(BaseModel):
    tool_name: str
    params: dict[str, Any]
    execution_id: str


class SSEToolResultEvent(BaseModel):
    execution_id: str
    result: Any
    status: str  # "success" | "failed"


class SSEHITLPendingEvent(BaseModel):
    execution_id: str
    tool_name: str
    params: dict[str, Any]
    schema_: dict[str, Any] = Field(alias="schema")


class SSETodoStateEvent(BaseModel):
    task_id: str
    steps: list[TodoStepResponse]


class SSEMessageEvent(BaseModel):
    content: str


class SSEErrorEvent(BaseModel):
    code: str
    message: str
