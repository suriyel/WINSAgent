"""
Human-in-the-Loop Protocol Module

Centralized definitions for HITL communication between frontend and backend.
Provides type-safe encoding/decoding of HITL messages and config builders.
"""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator
from langchain_core.messages import HumanMessage, BaseMessage
import json

from .state import PendingConfigField


class HITLAction(str, Enum):
    """User action types for HITL interrupts"""
    APPROVE = "approve"    # Authorization: execute with original args
    EDIT = "edit"          # Authorization: execute with modified args
    CONFIRM = "confirm"    # Param required: confirm provided params
    REJECT = "reject"      # Authorization: reject execution
    CANCEL = "cancel"      # Param required: cancel operation


class HITLResumeRequest(BaseModel):
    """
    Request model for /resume endpoint - validates frontend input.
    Supports both new 'action' field and legacy '_action' field.
    """
    action: HITLAction
    values: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='before')
    @classmethod
    def handle_legacy_action(cls, data: Any) -> Any:
        """Backward compat: accept _action as alias for action"""
        if isinstance(data, dict):
            if '_action' in data and 'action' not in data:
                data['action'] = data.pop('_action')
        return data


class HITLResumeData(BaseModel):
    """
    Parsed HITL resume data for executor consumption.
    Decoded from HumanMessage content by HITLMessageDecoder.
    """
    action: HITLAction
    tool_args: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_cancellation(self) -> bool:
        """Check if this is a cancellation action (reject/cancel)"""
        return self.action in (HITLAction.REJECT, HITLAction.CANCEL)

    @property
    def is_approval(self) -> bool:
        """Check if this is an approval action (approve/edit/confirm)"""
        return self.action in (HITLAction.APPROVE, HITLAction.EDIT, HITLAction.CONFIRM)


class HITLMessageEncoder:
    """
    Encodes HITL resume data into HumanMessage for graph state.

    The encoder translates user actions into structured messages that
    can be stored in the graph state and later decoded by the executor.
    """

    PREFIX_MAP: dict[HITLAction, str] = {
        HITLAction.APPROVE: "HITL_APPROVED:",
        HITLAction.EDIT: "HITL_EDITED:",
        HITLAction.CONFIRM: "HITL_PARAM:",
        HITLAction.REJECT: "HITL_REJECTED:",
        HITLAction.CANCEL: "HITL_CANCELLED:",
    }

    @classmethod
    def encode(
        cls,
        action: HITLAction,
        values: dict[str, Any],
        pending_config: dict | None = None,
    ) -> HumanMessage:
        """
        Encode resume request to HumanMessage for graph state.

        Args:
            action: The HITL action taken by the user
            values: Form values submitted by the user
            pending_config: Current pending config from state (for merging args)

        Returns:
            HumanMessage with encoded HITL data
        """
        prefix = cls.PREFIX_MAP.get(action)
        if not prefix:
            raise ValueError(f"Unknown HITL action: {action}")

        # Determine payload based on action type
        if action == HITLAction.APPROVE:
            # Use original tool args
            payload = pending_config.get("tool_args", {}) if pending_config else {}

        elif action == HITLAction.EDIT:
            # Use user-modified values
            payload = values

        elif action == HITLAction.CONFIRM:
            # Merge original args with user-provided values
            original = pending_config.get("tool_args", {}) if pending_config else {}
            payload = {**original, **values}

        elif action in (HITLAction.REJECT, HITLAction.CANCEL):
            # Include reason for cancellation
            payload = {"reason": f"user_{action.value}"}

        else:
            raise ValueError(f"Unhandled HITL action: {action}")

        content = f"{prefix}{json.dumps(payload, ensure_ascii=False)}"
        return HumanMessage(content=content, additional_kwargs={"metadata": {"internal": True}})


class HITLMessageDecoder:
    """
    Decodes HumanMessage to HITLResumeData.

    The decoder extracts HITL data from messages in the graph state,
    allowing the executor to determine if/how to resume execution.
    """

    PREFIX_MAP: dict[str, HITLAction] = {
        "HITL_APPROVED:": HITLAction.APPROVE,
        "HITL_EDITED:": HITLAction.EDIT,
        "HITL_PARAM:": HITLAction.CONFIRM,
        "HITL_REJECTED:": HITLAction.REJECT,
        "HITL_CANCELLED:": HITLAction.CANCEL,
    }

    @classmethod
    def decode(cls, message: BaseMessage | str) -> HITLResumeData | None:
        """
        Decode message to HITLResumeData.

        Args:
            message: A LangChain message or string to decode

        Returns:
            HITLResumeData if message is a HITL message, None otherwise
        """
        content = message.content if hasattr(message, 'content') else str(message)

        for prefix, action in cls.PREFIX_MAP.items():
            if content.startswith(prefix):
                data_str = content[len(prefix):]
                try:
                    payload = json.loads(data_str)
                except json.JSONDecodeError:
                    payload = {}

                # Cancellation actions don't carry tool args
                tool_args = {} if action in (HITLAction.REJECT, HITLAction.CANCEL) else payload

                return HITLResumeData(action=action, tool_args=tool_args)

        return None

    @classmethod
    def is_hitl_message(cls, message: BaseMessage | str) -> bool:
        """
        Check if message is a HITL resume message.

        Args:
            message: A LangChain message or string to check

        Returns:
            True if the message is a HITL message
        """
        content = message.content if hasattr(message, 'content') else str(message)
        return any(content.startswith(p) for p in cls.PREFIX_MAP)


# ============================================================================
# Config Builders - Create PendingConfig for different interrupt scenarios
# ============================================================================

def create_authorization_config(
    step_id: str,
    tool_name: str,
    tool_description: str,
    tool_args: dict[str, Any],
    fields: list[PendingConfigField],
) -> dict:
    """
    Create PendingConfig for authorization interrupt.

    Used when a tool requires user approval before execution.
    User can approve (with original args), edit (modify args), or reject.

    Args:
        step_id: ID of the current execution step
        tool_name: Name of the tool requiring authorization
        tool_description: Description of what the tool does
        tool_args: Arguments that will be passed to the tool
        fields: Form fields for editing (generated from tool schema)

    Returns:
        PendingConfig dict for frontend rendering
    """
    return {
        "step_id": step_id,
        "title": f"Tool Authorization: {tool_name}",
        "description": f"About to execute {tool_name}. Please review and authorize.\n\n{tool_description}",
        "fields": fields,
        "values": tool_args,
        "interrupt_type": "authorization",
        "tool_name": tool_name,
        "tool_args": tool_args,
    }


def create_param_required_config(
    step_id: str,
    tool_name: str,
    missing_fields: list[PendingConfigField],
    partial_args: dict[str, Any],
) -> dict:
    """
    Create PendingConfig for missing parameter interrupt.

    Used when a tool call is missing required parameters.
    User must provide the missing values to continue.

    Args:
        step_id: ID of the current execution step
        tool_name: Name of the tool with missing params
        missing_fields: Form fields for the missing parameters
        partial_args: Arguments that were already provided

    Returns:
        PendingConfig dict for frontend rendering
    """
    return {
        "step_id": step_id,
        "title": f"Parameters Required: {tool_name}",
        "description": f"Tool {tool_name} requires additional parameters.",
        "fields": missing_fields,
        "values": partial_args,
        "interrupt_type": "param_required",
        "tool_name": tool_name,
        "tool_args": partial_args,
    }


def create_user_input_config(
    step_id: str,
    description: str,
) -> dict:
    """
    Create PendingConfig for user input request.

    Used when the workflow needs direct user input (not tool-related).
    Presents a simple text area for the user to provide a response.

    Args:
        step_id: ID of the current execution step
        description: Description/prompt for the user

    Returns:
        PendingConfig dict for frontend rendering
    """
    return {
        "step_id": step_id,
        "title": "Input Required",
        "description": description,
        "fields": [{
            "name": "user_response",
            "label": "Your Response",
            "field_type": "textarea",
            "required": True,
            "default": None,
            "options": None,
            "placeholder": "Please enter your response...",
            "description": description,
            "children": None,
            "item_type": None,
        }],
        "values": {},
        "interrupt_type": "param_required",
        "tool_name": "user_input",
        "tool_args": {},
    }
