"""Shared fixtures for SubAgent framework tests.

- Unit tests (default): use mocked LLM, no real API calls.
- Live tests (pytest.mark.live): use real .env settings and LLM API.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend/app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Mock settings for unit tests
# ---------------------------------------------------------------------------

_mock_settings = MagicMock()
_mock_settings.llm_model = "test-model"
_mock_settings.llm_api_key = "sk-test-key"
_mock_settings.llm_base_url = "http://localhost:11434/v1"
_mock_settings.subagent_model = ""


@pytest.fixture(autouse=True)
def patch_settings(request):
    """Patch settings globally for unit tests; skip for live tests."""
    if request.node.get_closest_marker("live"):
        # Live tests use real settings from .env
        yield None
        return

    with patch("app.config.settings", _mock_settings):
        with patch("app.agent.subagents.runner.settings", _mock_settings):
            yield _mock_settings


# ---------------------------------------------------------------------------
# Live test helpers
# ---------------------------------------------------------------------------

def _load_real_settings():
    """Load real settings from .env (for live tests)."""
    from app.config import Settings
    return Settings()


@pytest.fixture
def real_settings():
    """Provide real settings loaded from .env."""
    return _load_real_settings()


@pytest.fixture
def real_llm():
    """Create a real ChatOpenAI instance from .env config."""
    from langchain_openai import ChatOpenAI
    s = _load_real_settings()
    return ChatOpenAI(
        model=s.subagent_model or s.llm_model,
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        streaming=False,
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "live: tests that call real LLM API (require .env)")


# ---------------------------------------------------------------------------
# Unit test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    """Create a mock ChatOpenAI instance."""
    llm = MagicMock()
    response = MagicMock()
    response.content = '[{"content": "步骤1", "status": "completed"}]'
    llm.invoke.return_value = response
    return llm


@pytest.fixture
def sample_ai_message():
    """Create a sample AIMessage."""
    from langchain_core.messages import AIMessage
    return AIMessage(content="分析完成，以下是根因分析结果...")


@pytest.fixture
def sample_human_message():
    """Create a sample HumanMessage."""
    from langchain_core.messages import HumanMessage
    return HumanMessage(content="请分析A区域弱覆盖问题")


@pytest.fixture
def sample_tool_message():
    """Create a sample ToolMessage."""
    from langchain_core.messages import ToolMessage
    return ToolMessage(content='{"result": "ok"}', tool_call_id="call_123", name="match_scenario")


@pytest.fixture
def sample_ai_with_tool_calls():
    """Create an AIMessage with tool_calls."""
    from langchain_core.messages import AIMessage
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "search_terminology", "args": {"query": "RSRP"}, "id": "tc_1"},
            {"name": "match_scenario", "args": {"area": "A"}, "id": "tc_2"},
        ],
    )


@pytest.fixture
def multi_turn_state(sample_human_message, sample_ai_with_tool_calls, sample_tool_message, sample_ai_message):
    """Simulate a multi-turn conversation state."""
    return {
        "messages": [
            sample_human_message,
            sample_ai_with_tool_calls,
            sample_tool_message,
            sample_ai_message,
        ],
        "todos": [
            {"content": "检索领域知识", "status": "completed"},
            {"content": "匹配仿真场景", "status": "in_progress"},
        ],
    }
