"""Tests for SubAgentRunner — compilation and invocation engine.

验证:
- compile(): Simple vs Full Agent 模式选择、缓存
- invoke_reactive(): 完整响应式调用流程、错误处理、fallback
- invoke_delegated(): 委派式调用、状态隔离
- _get_or_create_llm(): LLM 实例缓存
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.subagents.runner import SubAgentRunner
from app.agent.subagents.types import CompiledSubAgent, ReactiveSubAgentConfig, SubAgentConfig


# ===========================================================================
# 辅助工厂
# ===========================================================================

def _make_reactive_config(**overrides) -> ReactiveSubAgentConfig:
    """创建基本 ReactiveSubAgentConfig，可覆盖字段."""
    defaults: ReactiveSubAgentConfig = {
        "name": "test_reactive",
        "description": "测试响应式子 Agent",
        "system_prompt": "输出 JSON 数组",
        "trigger_hook": "after_model",
        "context_builder": lambda state: [HumanMessage(content="test context")],
        "result_parser": lambda raw: {"todos": [{"content": "步骤1", "status": "completed"}]},
        "owned_state_keys": ["todos"],
        "fallback_on_error": {},
    }
    defaults.update(overrides)
    return defaults


def _make_delegated_config(**overrides) -> SubAgentConfig:
    """创建基本 SubAgentConfig."""
    defaults: SubAgentConfig = {
        "name": "test_delegated",
        "description": "测试委派式子 Agent",
        "system_prompt": "你是数据分析专家",
        "tools": [MagicMock()],
    }
    defaults.update(overrides)
    return defaults


# ===========================================================================
# compile() 测试
# ===========================================================================


class TestCompile:
    """编译子 Agent 配置."""

    # --- Example 1: Simple 模式（无 tools） ---
    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_compile_simple_mode(self, MockChatOpenAI):
        """无 tools 的配置应编译为 Simple 模式."""
        MockChatOpenAI.return_value = MagicMock()
        runner = SubAgentRunner()
        config = _make_reactive_config()

        compiled = runner.compile(config)

        assert isinstance(compiled, CompiledSubAgent)
        assert compiled.is_simple_mode is True
        assert compiled.name == "test_reactive"
        assert compiled.llm is not None
        assert compiled.runnable is None

    # --- Example 2: Full Agent 模式（有 tools） ---
    @patch("app.agent.subagents.runner.create_agent")
    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_compile_full_agent_mode(self, MockChatOpenAI, mock_create_agent):
        """有 tools 的配置应编译为 Full Agent 模式."""
        MockChatOpenAI.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()
        runner = SubAgentRunner()

        config = _make_delegated_config()
        compiled = runner.compile(config)

        assert compiled.is_simple_mode is False
        assert compiled.runnable is not None
        mock_create_agent.assert_called_once()

    # --- Example 3: 缓存机制 ---
    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_compile_caching(self, MockChatOpenAI):
        """同名子 Agent 只编译一次."""
        MockChatOpenAI.return_value = MagicMock()
        runner = SubAgentRunner()
        config = _make_reactive_config()

        compiled1 = runner.compile(config)
        compiled2 = runner.compile(config)

        assert compiled1 is compiled2

    # --- Example 4: 不同名称编译为不同实例 ---
    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_compile_different_names(self, MockChatOpenAI):
        """不同名称的子 Agent 应编译为不同实例."""
        MockChatOpenAI.return_value = MagicMock()
        runner = SubAgentRunner()

        config_a = _make_reactive_config(name="agent_a")
        config_b = _make_reactive_config(name="agent_b")

        compiled_a = runner.compile(config_a)
        compiled_b = runner.compile(config_b)

        assert compiled_a is not compiled_b
        assert compiled_a.name == "agent_a"
        assert compiled_b.name == "agent_b"


# ===========================================================================
# invoke_reactive() 测试
# ===========================================================================


class TestInvokeReactive:
    """响应式调用: 不抛异常，返回 state 更新 dict."""

    # --- Example 5: 正常 Simple 模式调用 ---
    def test_simple_mode_invoke(self):
        """Simple 模式: LLM 输出 → result_parser → state 更新."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '[{"content": "分析数据", "status": "completed"}]'
        mock_llm.invoke.return_value = mock_response

        runner = SubAgentRunner()
        config = _make_reactive_config(
            result_parser=lambda raw: {"todos": [{"content": "分析数据", "status": "completed"}]}
        )
        compiled = CompiledSubAgent(
            name="test_reactive",
            description="test",
            config=config,
            llm=mock_llm,
        )

        state = {"messages": [HumanMessage(content="分析")], "todos": []}
        result = runner.invoke_reactive(compiled, state)

        assert result == {"todos": [{"content": "分析数据", "status": "completed"}]}
        mock_llm.invoke.assert_called_once()

    # --- Example 6: context_builder 返回 None → 跳过 ---
    def test_context_builder_returns_none_skips(self):
        """context_builder 返回 None 时应跳过调用."""
        runner = SubAgentRunner()
        config = _make_reactive_config(
            context_builder=lambda state: None,
        )
        compiled = CompiledSubAgent(
            name="skip_agent",
            description="test",
            config=config,
            llm=MagicMock(),
        )

        result = runner.invoke_reactive(compiled, {"messages": []})
        assert result == {}

    # --- Example 7: context_builder 异常 → fallback ---
    def test_context_builder_exception_returns_fallback(self):
        """context_builder 抛异常时应返回 fallback."""
        runner = SubAgentRunner()
        config = _make_reactive_config(
            context_builder=lambda state: (_ for _ in ()).throw(ValueError("boom")),
            fallback_on_error={"todos": []},
        )
        compiled = CompiledSubAgent(
            name="error_agent",
            description="test",
            config=config,
            llm=MagicMock(),
        )

        result = runner.invoke_reactive(compiled, {"messages": []})
        assert result == {"todos": []}

    # --- Example 8: LLM 调用异常 → fallback ---
    def test_llm_exception_returns_fallback(self):
        """LLM invoke 异常时应返回 fallback."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("LLM unavailable")

        runner = SubAgentRunner()
        config = _make_reactive_config(fallback_on_error={"todos": []})
        compiled = CompiledSubAgent(
            name="fail_agent",
            description="test",
            config=config,
            llm=mock_llm,
        )

        state = {"messages": [HumanMessage(content="test")]}
        result = runner.invoke_reactive(compiled, state)
        assert result == {"todos": []}

    # --- Example 9: result_parser 异常 → fallback ---
    def test_result_parser_exception_returns_fallback(self):
        """result_parser 抛异常时应返回 fallback."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "invalid output"
        mock_llm.invoke.return_value = mock_response

        runner = SubAgentRunner()
        config = _make_reactive_config(
            result_parser=lambda raw: (_ for _ in ()).throw(ValueError("parse error")),
            fallback_on_error={"todos": []},
        )
        compiled = CompiledSubAgent(
            name="parse_fail",
            description="test",
            config=config,
            llm=mock_llm,
        )

        result = runner.invoke_reactive(compiled, {"messages": [HumanMessage(content="test")]})
        assert result == {"todos": []}

    # --- Example 10: result_parser 返回非 dict → 空 dict ---
    def test_result_parser_returns_non_dict(self):
        """result_parser 返回 None/非 dict 时应返回空 dict."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "some output"
        mock_llm.invoke.return_value = mock_response

        runner = SubAgentRunner()
        config = _make_reactive_config(result_parser=lambda raw: None)
        compiled = CompiledSubAgent(
            name="none_parser",
            description="test",
            config=config,
            llm=mock_llm,
        )

        result = runner.invoke_reactive(compiled, {"messages": [HumanMessage(content="test")]})
        assert result == {}

    # --- Example 11: 无 result_parser + dict 输出 → owned_keys 提取 ---
    def test_no_parser_extracts_owned_keys(self):
        """无 result_parser 时，从 dict 输出提取 owned_state_keys."""
        mock_runnable = MagicMock()
        mock_runnable.invoke.return_value = {
            "messages": [],
            "todos": [{"content": "auto", "status": "completed"}],
            "other": "ignored",
        }

        runner = SubAgentRunner()
        config = _make_reactive_config()
        # 移除 result_parser
        del config["result_parser"]
        compiled = CompiledSubAgent(
            name="no_parser",
            description="test",
            config=config,
            runnable=mock_runnable,
        )

        result = runner.invoke_reactive(compiled, {"messages": [HumanMessage(content="test")]})
        assert "todos" in result
        assert "other" not in result

    # --- Example 12: 无 context_builder → fallback ---
    def test_missing_context_builder(self):
        """缺少 context_builder 时应返回 fallback."""
        runner = SubAgentRunner()
        config = _make_reactive_config(fallback_on_error={"todos": []})
        del config["context_builder"]
        compiled = CompiledSubAgent(
            name="no_ctx",
            description="test",
            config=config,
            llm=MagicMock(),
        )

        result = runner.invoke_reactive(compiled, {"messages": []})
        assert result == {"todos": []}


# ===========================================================================
# invoke_delegated() 测试
# ===========================================================================


class TestInvokeDelegated:
    """委派式调用: 状态隔离，返回文本."""

    # --- Example 13: 正常委派调用 ---
    def test_successful_delegation(self):
        """应传入 HumanMessage，返回 AIMessage 内容."""
        mock_runnable = MagicMock()
        mock_runnable.invoke.return_value = {
            "messages": [
                HumanMessage(content="任务"),
                AIMessage(content="分析结果: 弱覆盖原因是天线下倾角过大"),
            ]
        }

        runner = SubAgentRunner()
        compiled = CompiledSubAgent(
            name="analyst",
            description="分析子 Agent",
            config=_make_delegated_config(),
            runnable=mock_runnable,
        )

        result = runner.invoke_delegated(compiled, "请分析弱覆盖根因")

        assert "弱覆盖" in result
        assert "天线下倾角" in result
        # 验证传入了 HumanMessage
        call_args = mock_runnable.invoke.call_args[0][0]
        assert len(call_args["messages"]) == 1
        assert isinstance(call_args["messages"][0], HumanMessage)

    # --- Example 14: Simple 模式不能委派 ---
    def test_simple_mode_cannot_delegate(self):
        """Simple 模式的 compiled (无 runnable) 应返回错误提示."""
        runner = SubAgentRunner()
        compiled = CompiledSubAgent(
            name="simple_only",
            description="test",
            config=_make_reactive_config(),
            llm=MagicMock(),
        )

        result = runner.invoke_delegated(compiled, "任务描述")
        assert "无法委派" in result

    # --- Example 15: 委派调用异常 ---
    def test_delegation_exception(self):
        """委派调用异常时应返回错误信息."""
        mock_runnable = MagicMock()
        mock_runnable.invoke.side_effect = RuntimeError("子 Agent 崩溃")

        runner = SubAgentRunner()
        compiled = CompiledSubAgent(
            name="crash_agent",
            description="test",
            config=_make_delegated_config(),
            runnable=mock_runnable,
        )

        result = runner.invoke_delegated(compiled, "任务")
        assert "出错" in result

    # --- Example 16: 无 AIMessage 的返回 ---
    def test_no_ai_message_in_result(self):
        """结果中无 AIMessage 时应返回默认提示."""
        mock_runnable = MagicMock()
        mock_runnable.invoke.return_value = {
            "messages": [HumanMessage(content="只有这个")]
        }

        runner = SubAgentRunner()
        compiled = CompiledSubAgent(
            name="no_reply",
            description="test",
            config=_make_delegated_config(),
            runnable=mock_runnable,
        )

        result = runner.invoke_delegated(compiled, "任务")
        assert "未产生回复" in result


# ===========================================================================
# _get_or_create_llm() 测试
# ===========================================================================


class TestGetOrCreateLLM:
    """LLM 实例缓存."""

    # --- Example 17: 默认使用主模型 ---
    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_default_model(self, MockChatOpenAI):
        """无指定模型时应使用 settings.llm_model."""
        MockChatOpenAI.return_value = MagicMock()
        runner = SubAgentRunner()

        llm = runner._get_or_create_llm()

        MockChatOpenAI.assert_called_once()
        call_kwargs = MockChatOpenAI.call_args[1]
        assert call_kwargs["model"] == "test-model"

    # --- Example 18: 指定子 Agent 模型 ---
    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_custom_model(self, MockChatOpenAI):
        """指定模型时应使用该模型."""
        MockChatOpenAI.return_value = MagicMock()
        runner = SubAgentRunner()

        runner._get_or_create_llm("qwen-turbo")

        call_kwargs = MockChatOpenAI.call_args[1]
        assert call_kwargs["model"] == "qwen-turbo"

    # --- Example 19: LLM 缓存 ---
    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_llm_caching(self, MockChatOpenAI):
        """同一模型应只创建一次 ChatOpenAI 实例."""
        MockChatOpenAI.return_value = MagicMock()
        runner = SubAgentRunner()

        llm1 = runner._get_or_create_llm("model-a")
        llm2 = runner._get_or_create_llm("model-a")

        assert llm1 is llm2
        assert MockChatOpenAI.call_count == 1

    # --- Example 20: 不同模型创建不同实例 ---
    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_different_models_different_instances(self, MockChatOpenAI):
        """不同模型名应创建不同实例."""
        MockChatOpenAI.side_effect = [MagicMock(), MagicMock()]
        runner = SubAgentRunner()

        llm1 = runner._get_or_create_llm("model-a")
        llm2 = runner._get_or_create_llm("model-b")

        assert llm1 is not llm2
        assert MockChatOpenAI.call_count == 2
