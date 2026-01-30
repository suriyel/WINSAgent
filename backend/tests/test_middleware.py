"""Tests for SubAgentMiddleware — unified middleware for delegated + reactive sub-agents.

验证:
- 初始化: delegated / reactive 预编译
- tools 属性: task() tool 注入
- after_model(): 触发条件、调用、合并更新
- task() tool: 路由、未知名称处理
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.subagents.types import ReactiveSubAgentConfig, SubAgentConfig


# ===========================================================================
# 辅助工厂
# ===========================================================================

def _make_reactive(**overrides) -> ReactiveSubAgentConfig:
    defaults: ReactiveSubAgentConfig = {
        "name": "reactive_test",
        "description": "测试响应式",
        "system_prompt": "输出 JSON",
        "trigger_hook": "after_model",
        "context_builder": lambda state: [HumanMessage(content="ctx")],
        "result_parser": lambda raw: {"todos": [{"content": "done", "status": "completed"}]},
        "owned_state_keys": ["todos"],
        "fallback_on_error": {},
    }
    defaults.update(overrides)
    return defaults


def _make_delegated(**overrides) -> SubAgentConfig:
    defaults: SubAgentConfig = {
        "name": "delegated_test",
        "description": "测试委派式数据分析",
        "system_prompt": "你是分析师",
        "tools": [MagicMock()],
    }
    defaults.update(overrides)
    return defaults


# ===========================================================================
# 初始化测试
# ===========================================================================


class TestMiddlewareInit:
    """SubAgentMiddleware 初始化."""

    # --- Example 1: 空初始化 ---
    @patch("app.agent.subagents.middleware.SubAgentRunner")
    def test_empty_init(self, MockRunner):
        """无委派、无响应式时应正常初始化."""
        MockRunner.return_value = MagicMock()
        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(delegated=[], reactive=[])
        assert mw.tools == []

    # --- Example 2: 仅 reactive ---
    @patch("app.agent.subagents.middleware.SubAgentRunner")
    def test_reactive_only(self, MockRunner):
        """仅响应式子 Agent 时，无 task tool."""
        mock_runner = MagicMock()
        mock_runner.compile.return_value = MagicMock()
        MockRunner.return_value = mock_runner

        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(reactive=[_make_reactive()])
        assert mw.tools == []  # 无 delegated → 无 task tool
        mock_runner.compile.assert_called_once()

    # --- Example 3: 仅 delegated ---
    @patch("app.agent.subagents.middleware.SubAgentRunner")
    def test_delegated_only(self, MockRunner):
        """仅委派式子 Agent 时，应生成 task tool."""
        mock_compiled = MagicMock()
        mock_compiled.description = "测试描述"
        mock_runner = MagicMock()
        mock_runner.compile.return_value = mock_compiled
        MockRunner.return_value = mock_runner

        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(delegated=[_make_delegated()])
        assert len(mw.tools) == 1  # task tool

    # --- Example 4: 混合 delegated + reactive ---
    @patch("app.agent.subagents.middleware.SubAgentRunner")
    def test_mixed_init(self, MockRunner):
        """同时有 delegated + reactive 应都正确编译."""
        mock_compiled = MagicMock()
        mock_compiled.description = "desc"
        mock_runner = MagicMock()
        mock_runner.compile.return_value = mock_compiled
        MockRunner.return_value = mock_runner

        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(
            delegated=[_make_delegated()],
            reactive=[_make_reactive(), _make_reactive(name="reactive_2")],
        )
        assert len(mw.tools) == 1
        # compile 被调用 3 次（1 delegated + 2 reactive）
        assert mock_runner.compile.call_count == 3


# ===========================================================================
# after_model() Hook 测试
# ===========================================================================


class TestAfterModel:
    """after_model hook: 自动触发响应式子 Agent."""

    def _create_middleware_with_reactive(self, reactive_configs, runner_results=None):
        """辅助: 创建带 mock runner 的 middleware."""
        with patch("app.agent.subagents.middleware.SubAgentRunner") as MockRunner:
            mock_runner = MagicMock()
            mock_compiled = MagicMock()
            mock_runner.compile.return_value = mock_compiled
            if runner_results is not None:
                mock_runner.invoke_reactive.side_effect = runner_results
            else:
                mock_runner.invoke_reactive.return_value = {"todos": [{"content": "s", "status": "completed"}]}
            MockRunner.return_value = mock_runner

            from app.agent.subagents.middleware import SubAgentMiddleware
            mw = SubAgentMiddleware(reactive=reactive_configs)
            return mw, mock_runner

    # --- Example 5: 无 reactive → 返回 None ---
    def test_no_reactive_returns_none(self):
        """无响应式子 Agent 时 after_model 应返回 None."""
        with patch("app.agent.subagents.middleware.SubAgentRunner"):
            from app.agent.subagents.middleware import SubAgentMiddleware
            mw = SubAgentMiddleware(reactive=[])

        mock_runtime = MagicMock()
        result = mw.after_model({"messages": [AIMessage(content="hi")], "todos": []}, mock_runtime)
        assert result is None

    # --- Example 6: trigger_condition=True → 触发 ---
    def test_trigger_condition_true_fires(self):
        """trigger_condition 返回 True 时应调用子 Agent."""
        config = _make_reactive(trigger_condition=lambda s: True)
        mw, mock_runner = self._create_middleware_with_reactive([config])

        mock_runtime = MagicMock()
        state = {"messages": [AIMessage(content="test")], "todos": []}
        result = mw.after_model(state, mock_runtime)

        assert result is not None
        mock_runner.invoke_reactive.assert_called_once()

    # --- Example 7: trigger_condition=False → 跳过 ---
    def test_trigger_condition_false_skips(self):
        """trigger_condition 返回 False 时不应调用子 Agent."""
        config = _make_reactive(trigger_condition=lambda s: False)
        mw, mock_runner = self._create_middleware_with_reactive([config])

        mock_runtime = MagicMock()
        state = {"messages": [AIMessage(content="test")], "todos": []}
        result = mw.after_model(state, mock_runtime)

        assert result is None
        mock_runner.invoke_reactive.assert_not_called()

    # --- Example 8: 无 trigger_condition → 始终触发 ---
    def test_no_trigger_condition_always_fires(self):
        """无 trigger_condition 时应始终触发."""
        config = _make_reactive()
        # 移除 trigger_condition
        if "trigger_condition" in config:
            del config["trigger_condition"]

        mw, mock_runner = self._create_middleware_with_reactive([config])

        mock_runtime = MagicMock()
        state = {"messages": [AIMessage(content="test")], "todos": []}
        result = mw.after_model(state, mock_runtime)

        assert result is not None
        mock_runner.invoke_reactive.assert_called_once()

    # --- Example 9: trigger_condition 抛异常 → 跳过该 Agent ---
    def test_trigger_condition_exception_skips(self):
        """trigger_condition 异常时应跳过该子 Agent."""
        def bad_condition(s):
            raise ValueError("condition error")

        config = _make_reactive(trigger_condition=bad_condition)
        mw, mock_runner = self._create_middleware_with_reactive([config])

        mock_runtime = MagicMock()
        state = {"messages": [AIMessage(content="test")], "todos": []}
        result = mw.after_model(state, mock_runtime)

        assert result is None
        mock_runner.invoke_reactive.assert_not_called()

    # --- Example 10: 多个 reactive 合并更新 ---
    def test_multiple_reactive_merge_updates(self):
        """多个响应式子 Agent 的更新应合并."""
        config_a = _make_reactive(name="tracker_a", trigger_condition=lambda s: True)
        config_b = _make_reactive(name="tracker_b", trigger_condition=lambda s: True)

        with patch("app.agent.subagents.middleware.SubAgentRunner") as MockRunner:
            mock_runner = MagicMock()
            compiled_a = MagicMock()
            compiled_b = MagicMock()
            mock_runner.compile.side_effect = [compiled_a, compiled_b]
            mock_runner.invoke_reactive.side_effect = [
                {"todos": [{"content": "from A", "status": "completed"}]},
                {"metrics": [{"name": "RSRP", "value": -100}]},
            ]
            MockRunner.return_value = mock_runner

            from app.agent.subagents.middleware import SubAgentMiddleware
            mw = SubAgentMiddleware(reactive=[config_a, config_b])

        mock_runtime = MagicMock()
        state = {"messages": [AIMessage(content="test")], "todos": []}
        result = mw.after_model(state, mock_runtime)

        assert result is not None
        assert "todos" in result
        assert "metrics" in result

    # --- Example 11: invoke_reactive 返回空 dict → 不合并 ---
    def test_empty_update_skipped(self):
        """invoke_reactive 返回空 dict 时不合并."""
        config = _make_reactive(trigger_condition=lambda s: True)

        with patch("app.agent.subagents.middleware.SubAgentRunner") as MockRunner:
            mock_runner = MagicMock()
            mock_runner.compile.return_value = MagicMock()
            mock_runner.invoke_reactive.return_value = {}
            MockRunner.return_value = mock_runner

            from app.agent.subagents.middleware import SubAgentMiddleware
            mw = SubAgentMiddleware(reactive=[config])

        mock_runtime = MagicMock()
        result = mw.after_model({"messages": [AIMessage(content="test")], "todos": []}, mock_runtime)
        assert result is None


# ===========================================================================
# task() Tool 测试
# ===========================================================================


class TestTaskTool:
    """task() tool: 委派式子 Agent 路由."""

    # --- Example 12: 正常路由 ---
    @patch("app.agent.subagents.middleware.SubAgentRunner")
    def test_task_routes_correctly(self, MockRunner):
        """task(agent_name, description) 应路由到对应子 Agent."""
        mock_compiled = MagicMock()
        mock_compiled.description = "分析师"
        mock_runner = MagicMock()
        mock_runner.compile.return_value = mock_compiled
        mock_runner.invoke_delegated.return_value = "分析完成"
        MockRunner.return_value = mock_runner

        from app.agent.subagents.middleware import SubAgentMiddleware
        mw = SubAgentMiddleware(delegated=[_make_delegated()])

        task_tool = mw.tools[0]
        result = task_tool.invoke({"agent_name": "delegated_test", "task_description": "分析弱覆盖"})

        assert "分析完成" in result
        mock_runner.invoke_delegated.assert_called_once()

    # --- Example 13: 未知 agent_name ---
    @patch("app.agent.subagents.middleware.SubAgentRunner")
    def test_task_unknown_agent(self, MockRunner):
        """未知 agent_name 应返回错误提示."""
        mock_compiled = MagicMock()
        mock_compiled.description = "分析师"
        mock_runner = MagicMock()
        mock_runner.compile.return_value = mock_compiled
        MockRunner.return_value = mock_runner

        from app.agent.subagents.middleware import SubAgentMiddleware
        mw = SubAgentMiddleware(delegated=[_make_delegated()])

        task_tool = mw.tools[0]
        result = task_tool.invoke({"agent_name": "不存在的agent", "task_description": "任务"})

        assert "未知" in result
        assert "delegated_test" in result  # 提示可用名称
