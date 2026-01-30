"""Tests for SubAgent type definitions.

验证:
- CompiledSubAgent Simple/Full 模式判定
- SubAgentConfig / ReactiveSubAgentConfig 字典结构
- ContextBuilder / ResultParser 类型可调用
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.agent.subagents.types import (
    CompiledSubAgent,
    ReactiveSubAgentConfig,
    SubAgentConfig,
)


# ---------------------------------------------------------------------------
# Example 1: CompiledSubAgent — Simple 模式
# ---------------------------------------------------------------------------

class TestCompiledSubAgentSimpleMode:
    """Simple 模式: llm 不为 None, runnable 为 None."""

    def test_simple_mode_detection(self):
        """is_simple_mode 应返回 True."""
        compiled = CompiledSubAgent(
            name="test_simple",
            description="测试 Simple 子 Agent",
            config={"name": "test_simple", "description": "test", "system_prompt": "你好"},
            llm=MagicMock(),  # 有 LLM
            runnable=None,     # 无 runnable
        )
        assert compiled.is_simple_mode is True

    def test_simple_mode_fields(self):
        """Simple 模式下 llm 应存在，runnable 应为 None."""
        mock_llm = MagicMock()
        compiled = CompiledSubAgent(
            name="simple_agent",
            description="Simple 模式测试",
            config={"name": "simple_agent", "description": "test", "system_prompt": "prompt"},
            llm=mock_llm,
        )
        assert compiled.llm is mock_llm
        assert compiled.runnable is None
        assert compiled.name == "simple_agent"
        assert compiled.description == "Simple 模式测试"


# ---------------------------------------------------------------------------
# Example 2: CompiledSubAgent — Full Agent 模式
# ---------------------------------------------------------------------------

class TestCompiledSubAgentFullMode:
    """Full Agent 模式: runnable 不为 None."""

    def test_full_mode_detection(self):
        """is_simple_mode 应返回 False."""
        compiled = CompiledSubAgent(
            name="test_full",
            description="测试 Full Agent 子 Agent",
            config={"name": "test_full", "description": "test", "system_prompt": "你好"},
            runnable=MagicMock(),  # 有 runnable
            llm=None,              # 无 LLM (Full 模式不直接用)
        )
        assert compiled.is_simple_mode is False

    def test_both_none_is_neither_mode(self):
        """llm 和 runnable 都为 None 时不应判定为 Simple 模式."""
        compiled = CompiledSubAgent(
            name="empty",
            description="空",
            config={"name": "empty", "description": "empty", "system_prompt": "x"},
        )
        assert compiled.is_simple_mode is False
        assert compiled.runnable is None
        assert compiled.llm is None


# ---------------------------------------------------------------------------
# Example 3: SubAgentConfig — 委派式子 Agent 配置
# ---------------------------------------------------------------------------

class TestSubAgentConfig:
    """验证委派式子 Agent 配置字典结构."""

    def test_minimal_config(self):
        """最小必填字段验证."""
        config: SubAgentConfig = {
            "name": "data_analyst",
            "description": "数据分析子 Agent",
            "system_prompt": "你是一个数据分析专家",
            "tools": [MagicMock()],
        }
        assert config["name"] == "data_analyst"
        assert config["description"] == "数据分析子 Agent"
        assert len(config["tools"]) == 1

    def test_config_with_optional_fields(self):
        """包含可选字段的配置."""
        config: SubAgentConfig = {
            "name": "optimizer",
            "description": "优化仿真子 Agent",
            "system_prompt": "你是优化仿真专家",
            "tools": [MagicMock(), MagicMock()],
            "model": "qwen-turbo",
            "middleware": [],
        }
        assert config.get("model") == "qwen-turbo"
        assert config.get("middleware") == []


# ---------------------------------------------------------------------------
# Example 4: ReactiveSubAgentConfig — 响应式子 Agent 配置
# ---------------------------------------------------------------------------

class TestReactiveSubAgentConfig:
    """验证响应式子 Agent 配置字典结构."""

    def test_todo_tracker_config_structure(self):
        """验证 TODO tracker 风格的配置结构."""
        from app.agent.subagents.agents.todo_tracker import TODO_TRACKER_CONFIG

        cfg = TODO_TRACKER_CONFIG
        assert cfg["name"] == "todo_tracker"
        assert cfg["trigger_hook"] == "after_model"
        assert callable(cfg["trigger_condition"])
        assert callable(cfg["context_builder"])
        assert callable(cfg["result_parser"])
        assert "todos" in cfg["owned_state_keys"]
        # Simple 模式: 无 tools
        assert cfg.get("tools") is None or len(cfg.get("tools", [])) == 0

    def test_custom_reactive_config(self):
        """自定义响应式配置示例."""
        def my_context_builder(state):
            return None

        def my_parser(raw):
            return {"metrics": []}

        def always_fire(state):
            return True

        config: ReactiveSubAgentConfig = {
            "name": "metrics_tracker",
            "description": "指标追踪子 Agent",
            "system_prompt": "你负责追踪分析指标",
            "trigger_hook": "after_model",
            "trigger_condition": always_fire,
            "context_builder": my_context_builder,
            "result_parser": my_parser,
            "owned_state_keys": ["metrics"],
            "fallback_on_error": {"metrics": []},
        }
        assert config["name"] == "metrics_tracker"
        assert config["trigger_hook"] == "after_model"
        assert config["context_builder"]({}) is None
        assert config["result_parser"]("test") == {"metrics": []}
        assert config["fallback_on_error"] == {"metrics": []}


# ---------------------------------------------------------------------------
# Example 5: ContextBuilder / ResultParser 可调用类型
# ---------------------------------------------------------------------------

class TestCallableTypes:
    """验证 ContextBuilder 和 ResultParser 作为 Callable 的用法."""

    def test_context_builder_returns_messages(self):
        """ContextBuilder 应返回消息列表或 None."""
        from langchain_core.messages import HumanMessage

        def builder(state):
            if not state.get("messages"):
                return None
            return [HumanMessage(content="summarized context")]

        # 有消息时返回列表
        result = builder({"messages": [MagicMock()]})
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

        # 无消息时返回 None
        assert builder({"messages": []}) is None

    def test_result_parser_returns_dict_or_none(self):
        """ResultParser 应返回 dict 或 None."""
        import json

        def parser(raw: str):
            try:
                data = json.loads(raw)
                return {"todos": data} if isinstance(data, list) else None
            except (json.JSONDecodeError, TypeError):
                return None

        # 有效 JSON
        assert parser('[{"content": "步骤1", "status": "completed"}]') == {
            "todos": [{"content": "步骤1", "status": "completed"}]
        }
        # 无效 JSON
        assert parser("not json") is None
        # 非数组
        assert parser('{"key": "value"}') is None
