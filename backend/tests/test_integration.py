"""Integration tests — end-to-end SubAgent framework pipeline simulation.

验证:
- 完整 TODO tracker 流程: state → context_builder → LLM → result_parser → state update
- 多轮对话场景下 TODO 状态演进
- SubAgentMiddleware + SubAgentRunner 联动
- 委派式 + 响应式混合场景
- 错误恢复: LLM 异常、解析失败不影响主流程
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.subagents.agents.todo_tracker import (
    TODO_TRACKER_CONFIG,
    build_todo_context,
    parse_todo_result,
    should_fire,
)
from app.agent.subagents.runner import SubAgentRunner
from app.agent.subagents.types import (
    CompiledSubAgent,
    ReactiveSubAgentConfig,
    SubAgentConfig,
)


# ===========================================================================
# Example 1: TODO Tracker 完整流程 — 首轮对话
# ===========================================================================


class TestTodoTrackerE2EFirstTurn:
    """首轮对话: 用户发送任务 → AI 开始分析 → TODO 自动生成."""

    def test_first_turn_generates_initial_todos(self):
        """首轮对话后应生成初始 TODO 步骤列表."""
        # 模拟首轮对话 state
        state = {
            "messages": [
                HumanMessage(content="请分析A区域的弱覆盖问题"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "search_terminology", "args": {"query": "弱覆盖"}, "id": "tc_1"}],
                ),
                ToolMessage(content='{"terms": ["RSRP", "覆盖率"]}', tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="已获取术语定义，正在检索分析流程..."),
            ],
            "todos": [],
        }

        # Step 1: 验证触发条件
        assert should_fire(state) is True

        # Step 2: 构建上下文
        context = build_todo_context(state)
        assert context is not None
        assert len(context) == 1
        content = context[0].content
        assert "请分析A区域的弱覆盖问题" in content
        assert "创建初始步骤" in content  # 无 todos 时提示创建
        assert "search_terminology" in content

        # Step 3: 模拟 LLM 输出
        llm_output = json.dumps([
            {"content": "检索领域知识和术语定义", "status": "completed"},
            {"content": "检索分析流程文档", "status": "in_progress"},
            {"content": "匹配仿真场景", "status": "pending"},
            {"content": "执行根因分析", "status": "pending"},
        ])

        # Step 4: 解析结果
        result = parse_todo_result(llm_output)
        assert result is not None
        assert len(result["todos"]) == 4
        assert result["todos"][0]["status"] == "completed"
        assert result["todos"][1]["status"] == "in_progress"
        assert result["todos"][2]["status"] == "pending"


# ===========================================================================
# Example 2: TODO Tracker 完整流程 — 中期对话（状态演进）
# ===========================================================================


class TestTodoTrackerE2EMidConversation:
    """中期对话: 已有 TODO，工具继续执行 → TODO 状态更新."""

    def test_mid_conversation_updates_todos(self):
        """已有 TODO 步骤在工具执行后应被更新."""
        state = {
            "messages": [
                HumanMessage(content="请分析A区域的弱覆盖问题"),
                AIMessage(content="", tool_calls=[{"name": "search_terminology", "args": {}, "id": "tc_1"}]),
                ToolMessage(content="ok", tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="", tool_calls=[{"name": "match_scenario", "args": {"area": "A"}, "id": "tc_2"}]),
                ToolMessage(content='{"digitaltwinsId": "dt_001"}', tool_call_id="tc_2", name="match_scenario"),
                AIMessage(content="", tool_calls=[{"name": "query_root_cause_analysis", "args": {}, "id": "tc_3"}]),
                ToolMessage(content='{"result": "弱覆盖根因..."}', tool_call_id="tc_3", name="query_root_cause_analysis"),
                AIMessage(content="根因分析完成。是否需要对该场景进行优化仿真？"),
            ],
            "todos": [
                {"content": "检索领域知识和术语定义", "status": "completed"},
                {"content": "匹配仿真场景", "status": "completed"},
                {"content": "执行根因分析", "status": "in_progress"},
                {"content": "展示分析结果", "status": "pending"},
            ],
        }

        # 验证触发
        assert should_fire(state) is True

        # 构建上下文 — 应包含现有 todos 和最近操作
        context = build_todo_context(state)
        content = context[0].content
        assert "检索领域知识" in content
        assert "执行根因分析" in content
        assert "in_progress" in content

        # 模拟 LLM 更新
        llm_output = json.dumps([
            {"content": "检索领域知识和术语定义", "status": "completed"},
            {"content": "匹配仿真场景", "status": "completed"},
            {"content": "执行根因分析", "status": "completed"},
            {"content": "展示分析结果", "status": "completed"},
        ])

        result = parse_todo_result(llm_output)
        assert all(t["status"] == "completed" for t in result["todos"])


# ===========================================================================
# Example 3: SubAgentRunner + TODO Tracker 联动
# ===========================================================================


class TestRunnerTodoTrackerIntegration:
    """SubAgentRunner 调用 TODO Tracker 的完整链路."""

    def test_runner_invokes_todo_tracker_simple_mode(self):
        """Runner 应以 Simple 模式调用 TODO Tracker 并返回 state 更新."""
        # Mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {"content": "检索知识", "status": "completed"},
            {"content": "匹配场景", "status": "in_progress"},
        ])
        mock_llm.invoke.return_value = mock_response

        # 构建 CompiledSubAgent（Simple 模式）
        compiled = CompiledSubAgent(
            name="todo_tracker",
            description="任务追踪",
            config=TODO_TRACKER_CONFIG,
            llm=mock_llm,
        )

        # 模拟 parent state
        state = {
            "messages": [
                HumanMessage(content="分析弱覆盖"),
                AIMessage(content="开始检索..."),
            ],
            "todos": [],
        }

        runner = SubAgentRunner()
        result = runner.invoke_reactive(compiled, state)

        assert "todos" in result
        assert len(result["todos"]) == 2
        assert result["todos"][0]["content"] == "检索知识"
        mock_llm.invoke.assert_called_once()

    def test_runner_with_malformed_llm_output(self):
        """LLM 输出非法 JSON 时应返回 fallback (空 dict)."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "这不是JSON，我是一个不守规矩的LLM"
        mock_llm.invoke.return_value = mock_response

        compiled = CompiledSubAgent(
            name="todo_tracker",
            description="任务追踪",
            config=TODO_TRACKER_CONFIG,
            llm=mock_llm,
        )

        state = {
            "messages": [HumanMessage(content="test"), AIMessage(content="reply")],
            "todos": [],
        }

        runner = SubAgentRunner()
        result = runner.invoke_reactive(compiled, state)

        # parse_todo_result 返回 None → invoke_reactive 返回 {}
        assert result == {}


# ===========================================================================
# Example 4: SubAgentMiddleware 集成 — after_model 完整链路
# ===========================================================================


class TestMiddlewareIntegration:
    """SubAgentMiddleware after_model → SubAgentRunner → TODO 更新."""

    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_middleware_after_model_produces_todos(self, MockChatOpenAI):
        """after_model 调用应产生 todos state 更新."""
        # Mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {"content": "开始分析", "status": "in_progress"},
        ])
        mock_llm.invoke.return_value = mock_response
        MockChatOpenAI.return_value = mock_llm

        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(reactive=[TODO_TRACKER_CONFIG])

        state = {
            "messages": [
                HumanMessage(content="分析弱覆盖"),
                AIMessage(content="正在分析..."),
            ],
            "todos": [],
        }

        mock_runtime = MagicMock()
        result = mw.after_model(state, mock_runtime)

        assert result is not None
        assert "todos" in result
        assert len(result["todos"]) == 1
        assert result["todos"][0]["content"] == "开始分析"

    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_middleware_skips_when_last_is_tool_message(self, MockChatOpenAI):
        """最后一条为 ToolMessage 时 should_fire=False → 不触发."""
        MockChatOpenAI.return_value = MagicMock()

        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(reactive=[TODO_TRACKER_CONFIG])

        state = {
            "messages": [
                HumanMessage(content="test"),
                ToolMessage(content="ok", tool_call_id="c1", name="t1"),
            ],
            "todos": [],
        }

        mock_runtime = MagicMock()
        result = mw.after_model(state, mock_runtime)
        assert result is None


# ===========================================================================
# Example 5: 多轮连续调用 — TODO 状态演进
# ===========================================================================


class TestMultiTurnTodoEvolution:
    """模拟 3 轮对话，验证 TODO 状态从 pending → in_progress → completed 演进."""

    def test_three_turn_evolution(self):
        """3 轮对话中 TODO 状态应逐步演进."""

        # --- Round 1: 用户提问 → AI 开始调用工具 ---
        state_r1 = {
            "messages": [
                HumanMessage(content="分析弱覆盖"),
                AIMessage(content="", tool_calls=[{"name": "search_terminology", "args": {}, "id": "tc_1"}]),
                ToolMessage(content="ok", tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="已获取术语，继续分析..."),
            ],
            "todos": [],
        }

        ctx_r1 = build_todo_context(state_r1)
        assert ctx_r1 is not None

        llm_r1_output = json.dumps([
            {"content": "检索领域知识", "status": "completed"},
            {"content": "匹配仿真场景", "status": "pending"},
            {"content": "执行根因分析", "status": "pending"},
        ])
        result_r1 = parse_todo_result(llm_r1_output)
        todos_r1 = result_r1["todos"]

        assert todos_r1[0]["status"] == "completed"
        assert todos_r1[1]["status"] == "pending"

        # --- Round 2: AI 继续调用工具 ---
        state_r2 = {
            "messages": state_r1["messages"] + [
                AIMessage(content="", tool_calls=[{"name": "match_scenario", "args": {}, "id": "tc_2"}]),
                ToolMessage(content='{"id": "dt_001"}', tool_call_id="tc_2", name="match_scenario"),
                AIMessage(content="场景匹配完成，开始根因分析..."),
            ],
            "todos": todos_r1,
        }

        ctx_r2 = build_todo_context(state_r2)
        content_r2 = ctx_r2[0].content
        assert "检索领域知识" in content_r2
        assert "completed" in content_r2

        llm_r2_output = json.dumps([
            {"content": "检索领域知识", "status": "completed"},
            {"content": "匹配仿真场景", "status": "completed"},
            {"content": "执行根因分析", "status": "in_progress"},
        ])
        result_r2 = parse_todo_result(llm_r2_output)
        todos_r2 = result_r2["todos"]

        assert todos_r2[1]["status"] == "completed"  # 从 pending → completed
        assert todos_r2[2]["status"] == "in_progress"

        # --- Round 3: 分析完成 ---
        state_r3 = {
            "messages": state_r2["messages"] + [
                AIMessage(content="", tool_calls=[{"name": "query_root_cause_analysis", "args": {}, "id": "tc_3"}]),
                ToolMessage(content='{"root_cause": "天线下倾角"}', tool_call_id="tc_3", name="query_root_cause_analysis"),
                AIMessage(content="根因分析完成。是否需要对该场景进行优化仿真？"),
            ],
            "todos": todos_r2,
        }

        llm_r3_output = json.dumps([
            {"content": "检索领域知识", "status": "completed"},
            {"content": "匹配仿真场景", "status": "completed"},
            {"content": "执行根因分析", "status": "completed"},
            {"content": "展示分析结果", "status": "completed"},
        ])
        result_r3 = parse_todo_result(llm_r3_output)
        todos_r3 = result_r3["todos"]

        # 所有步骤完成
        assert all(t["status"] == "completed" for t in todos_r3)
        assert len(todos_r3) == 4


# ===========================================================================
# Example 6: 混合场景 — delegated + reactive 共存
# ===========================================================================


class TestMixedDelegatedReactive:
    """委派式 + 响应式子 Agent 共存时互不干扰."""

    @patch("app.agent.subagents.runner.create_agent")
    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_delegated_and_reactive_coexist(self, MockChatOpenAI, mock_create_agent):
        """delegated + reactive 同时配置时均可正常工作."""
        # Mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {"content": "步骤A", "status": "completed"},
        ])
        mock_llm.invoke.return_value = mock_response
        MockChatOpenAI.return_value = mock_llm

        # Mock agent for delegated
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {
            "messages": [AIMessage(content="委派结果")]
        }
        mock_create_agent.return_value = mock_agent

        delegated_config: SubAgentConfig = {
            "name": "data_analyst",
            "description": "数据分析",
            "system_prompt": "你是分析师",
            "tools": [MagicMock()],
        }

        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(
            delegated=[delegated_config],
            reactive=[TODO_TRACKER_CONFIG],
        )

        # 验证 task tool 存在
        assert len(mw.tools) == 1

        # 验证 after_model 可触发 reactive
        state = {
            "messages": [HumanMessage(content="test"), AIMessage(content="reply")],
            "todos": [],
        }
        mock_runtime = MagicMock()
        result = mw.after_model(state, mock_runtime)
        assert result is not None
        assert "todos" in result

        # 验证 task tool 可路由到 delegated
        task_tool = mw.tools[0]
        task_result = task_tool.invoke({
            "agent_name": "data_analyst",
            "task_description": "分析数据",
        })
        assert "委派结果" in task_result


# ===========================================================================
# Example 7: 错误恢复 — LLM 异常不影响主流程
# ===========================================================================


class TestErrorRecovery:
    """子 Agent 异常时不应阻塞主 Agent."""

    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_llm_failure_returns_fallback(self, MockChatOpenAI):
        """LLM 调用失败时 after_model 应返回 None（fallback 为空 dict）."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("API timeout")
        MockChatOpenAI.return_value = mock_llm

        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(reactive=[TODO_TRACKER_CONFIG])

        state = {
            "messages": [HumanMessage(content="test"), AIMessage(content="reply")],
            "todos": [],
        }
        mock_runtime = MagicMock()
        result = mw.after_model(state, mock_runtime)

        # fallback_on_error = {} → merge 为空 → 返回 None
        assert result is None

    @patch("app.agent.subagents.runner.ChatOpenAI")
    def test_malformed_output_graceful_degradation(self, MockChatOpenAI):
        """LLM 返回非法输出时应优雅降级."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "我无法输出JSON，让我用文字描述..."
        mock_llm.invoke.return_value = mock_response
        MockChatOpenAI.return_value = mock_llm

        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(reactive=[TODO_TRACKER_CONFIG])

        state = {
            "messages": [HumanMessage(content="test"), AIMessage(content="reply")],
            "todos": [{"content": "现有步骤", "status": "in_progress"}],
        }
        mock_runtime = MagicMock()
        result = mw.after_model(state, mock_runtime)

        # parse_todo_result 返回 None → invoke_reactive 返回 {} → merge 为空
        assert result is None  # 不会破坏现有 todos


# ===========================================================================
# Example 8: 自定义 Reactive 子 Agent 扩展示例
# ===========================================================================


class TestCustomReactiveExtension:
    """演示如何通过框架添加新的 reactive 子 Agent."""

    def test_custom_metrics_tracker(self):
        """自定义 metrics_tracker 子 Agent 的完整链路."""

        # 自定义 context_builder
        def build_metrics_context(state):
            messages = state.get("messages", [])
            if not messages:
                return None
            return [HumanMessage(content="提取最近工具调用的性能指标")]

        # 自定义 result_parser
        def parse_metrics_result(raw):
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return {"metrics": data}
            except (json.JSONDecodeError, TypeError):
                pass
            return None

        # 自定义配置
        custom_config: ReactiveSubAgentConfig = {
            "name": "metrics_tracker",
            "description": "追踪分析指标",
            "system_prompt": "你负责从工具输出中提取关键指标，输出 JSON 数组",
            "trigger_hook": "after_model",
            "trigger_condition": lambda s: isinstance(s.get("messages", [])[-1], AIMessage) if s.get("messages") else False,
            "context_builder": build_metrics_context,
            "result_parser": parse_metrics_result,
            "owned_state_keys": ["metrics"],
            "fallback_on_error": {"metrics": []},
        }

        # 模拟 LLM 调用
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {"name": "RSRP", "value": -95, "unit": "dBm"},
            {"name": "MR覆盖率", "value": 78.5, "unit": "%"},
        ])
        mock_llm.invoke.return_value = mock_response

        compiled = CompiledSubAgent(
            name="metrics_tracker",
            description="追踪指标",
            config=custom_config,
            llm=mock_llm,
        )

        state = {
            "messages": [HumanMessage(content="分析"), AIMessage(content="结果")],
            "metrics": [],
        }

        runner = SubAgentRunner()
        result = runner.invoke_reactive(compiled, state)

        assert "metrics" in result
        assert len(result["metrics"]) == 2
        assert result["metrics"][0]["name"] == "RSRP"
        assert result["metrics"][1]["value"] == 78.5


# ===========================================================================
# Example 9: 自定义 Delegated 子 Agent 扩展示例
# ===========================================================================


class TestCustomDelegatedExtension:
    """演示如何通过框架添加新的 delegated 子 Agent."""

    def test_delegated_report_generator(self):
        """自定义报告生成器的委派调用."""
        mock_runnable = MagicMock()
        mock_runnable.invoke.return_value = {
            "messages": [
                HumanMessage(content="生成报告"),
                AIMessage(content="# 弱覆盖分析报告\n\n## 概要\n- 影响小区: 15个\n- 主要原因: 天线下倾角配置不当"),
            ]
        }

        delegated_config: SubAgentConfig = {
            "name": "report_generator",
            "description": "根据分析结果生成结构化报告",
            "system_prompt": "你是报告生成专家，根据分析结果输出 Markdown 格式报告",
            "tools": [MagicMock()],
        }

        compiled = CompiledSubAgent(
            name="report_generator",
            description="报告生成",
            config=delegated_config,
            runnable=mock_runnable,
        )

        runner = SubAgentRunner()
        result = runner.invoke_delegated(compiled, "根据根因分析结果生成报告，影响小区15个")

        assert "弱覆盖分析报告" in result
        assert "天线下倾角" in result

        # 验证状态隔离: 只传入了 HumanMessage
        call_args = mock_runnable.invoke.call_args[0][0]
        messages = call_args["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert "根因分析结果" in messages[0].content
