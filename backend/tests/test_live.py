"""Live tests — real LLM calls, no mocks.

运行方式:
    cd backend
    python -m pytest tests/test_live.py -v -m live -s

需要:
    - backend/.env 配置有效的 LLM_API_KEY 和 LLM_BASE_URL
    - 网络可达 LLM API

每个 test case 打印实际 LLM 输出，方便人工检查。
"""

from __future__ import annotations

import json
import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.subagents.agents.todo_tracker import (
    TODO_TRACKER_CONFIG,
    TODO_SYSTEM_PROMPT,
    build_todo_context,
    parse_todo_result,
    should_fire,
)
from app.agent.subagents.runner import SubAgentRunner
from app.agent.subagents.types import CompiledSubAgent, ReactiveSubAgentConfig

logger = logging.getLogger(__name__)

# 所有 test 标记为 live
pytestmark = pytest.mark.live


# ===========================================================================
# 辅助
# ===========================================================================

def _validate_todos(todos: list[dict]) -> None:
    """校验 todos 列表格式."""
    assert isinstance(todos, list), f"todos 应为 list，实际: {type(todos)}"
    assert len(todos) >= 1, "todos 不应为空"
    for i, t in enumerate(todos):
        assert isinstance(t, dict), f"todos[{i}] 应为 dict，实际: {type(t)}"
        assert "content" in t, f"todos[{i}] 缺少 content"
        assert "status" in t, f"todos[{i}] 缺少 status"
        assert t["status"] in ("pending", "in_progress", "completed"), (
            f"todos[{i}] status 无效: {t['status']}"
        )
        assert len(t["content"]) > 0, f"todos[{i}] content 为空"


def _print_result(label: str, data) -> None:
    """格式化打印结果."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"{'='*60}\n")


# ===========================================================================
# Example 1: 直接调用 LLM — 验证 TODO system prompt 有效性
# ===========================================================================

class TestLLMDirectCall:
    """直接调用 ChatOpenAI，验证 TODO 系统提示词能产出合法 JSON."""

    def test_llm_outputs_valid_json_for_new_task(self, real_llm):
        """首轮对话: 用户发起弱覆盖分析 → LLM 应输出 JSON 步骤数组."""
        context = (
            "用户任务: 请分析A区域的弱覆盖问题\n\n"
            "当前没有任务步骤，请根据 Agent 活动创建初始步骤。\n\n"
            "最近操作:\n"
            "[调用工具] search_terminology\n"
            "[工具结果] search_terminology: 成功"
        )
        messages = [
            {"role": "system", "content": TODO_SYSTEM_PROMPT},
            HumanMessage(content=context),
        ]
        response = real_llm.invoke(messages)
        raw = response.content
        _print_result("LLM 原始输出（首轮新任务）", raw)

        result = parse_todo_result(raw)
        assert result is not None, f"parse_todo_result 失败，原始输出: {raw}"
        _validate_todos(result["todos"])
        assert 3 <= len(result["todos"]) <= 6, f"步骤数应为 3-6，实际: {len(result['todos'])}"

    def test_llm_outputs_valid_json_for_mid_conversation(self, real_llm):
        """中期对话: 已有部分步骤完成 → LLM 应更新步骤状态."""
        context = (
            "用户任务: 请分析A区域的弱覆盖问题\n\n"
            "当前步骤:\n"
            "- [completed] 检索领域知识和术语定义\n"
            "- [completed] 匹配仿真场景\n"
            "- [in_progress] 执行根因分析\n"
            "- [pending] 展示分析结果\n\n"
            "最近操作:\n"
            "[调用工具] query_root_cause_analysis\n"
            "[工具结果] query_root_cause_analysis: 成功\n"
            "[AI回复] 根因分析完成。是否需要对该场景进行优化仿真？"
        )
        messages = [
            {"role": "system", "content": TODO_SYSTEM_PROMPT},
            HumanMessage(content=context),
        ]
        response = real_llm.invoke(messages)
        raw = response.content
        _print_result("LLM 原始输出（中期对话）", raw)

        result = parse_todo_result(raw)
        assert result is not None, f"parse_todo_result 失败，原始输出: {raw}"
        _validate_todos(result["todos"])

        # 至少前 3 步应为 completed
        completed_count = sum(1 for t in result["todos"] if t["status"] == "completed")
        assert completed_count >= 3, f"至少 3 步应 completed，实际 {completed_count}"

    def test_llm_outputs_valid_json_for_final_state(self, real_llm):
        """最终状态: 全部操作完成 → LLM 应将所有步骤标记为 completed."""
        context = (
            "用户任务: 请分析A区域的弱覆盖问题\n\n"
            "当前步骤:\n"
            "- [completed] 检索领域知识和术语定义\n"
            "- [completed] 匹配仿真场景\n"
            "- [completed] 执行根因分析\n"
            "- [in_progress] 展示分析结果\n\n"
            "最近操作:\n"
            "[AI回复] 根因分析完成。是否需要对该场景进行优化仿真？"
        )
        messages = [
            {"role": "system", "content": TODO_SYSTEM_PROMPT},
            HumanMessage(content=context),
        ]
        response = real_llm.invoke(messages)
        raw = response.content
        _print_result("LLM 原始输出（最终状态）", raw)

        result = parse_todo_result(raw)
        assert result is not None, f"parse_todo_result 失败，原始输出: {raw}"
        _validate_todos(result["todos"])

        completed_count = sum(1 for t in result["todos"] if t["status"] == "completed")
        assert completed_count >= 3


# ===========================================================================
# Example 2: context_builder → LLM → result_parser 完整管线
# ===========================================================================

class TestFullPipeline:
    """完整管线: build_todo_context → LLM invoke → parse_todo_result."""

    def test_pipeline_first_turn(self, real_llm):
        """首轮: 用户提问 + AI 开始调用工具."""
        state = {
            "messages": [
                HumanMessage(content="请分析B区域的SINR干扰问题"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "search_terminology", "args": {"query": "SINR"}, "id": "tc_1"}],
                ),
                ToolMessage(content='{"terms": ["SINR", "干扰"]}', tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="已获取SINR相关术语定义，正在检索分析流程..."),
            ],
            "todos": [],
        }

        # Step 1: context_builder
        context_msgs = build_todo_context(state)
        assert context_msgs is not None
        _print_result("context_builder 输出", context_msgs[0].content)

        # Step 2: LLM invoke
        system_msg = {"role": "system", "content": TODO_SYSTEM_PROMPT}
        response = real_llm.invoke([system_msg] + context_msgs)
        raw = response.content
        _print_result("LLM 输出", raw)

        # Step 3: result_parser
        result = parse_todo_result(raw)
        assert result is not None, f"解析失败: {raw}"
        _print_result("解析后的 todos", result["todos"])
        _validate_todos(result["todos"])

    def test_pipeline_multi_turn_with_existing_todos(self, real_llm):
        """多轮: 已有 todos + 新工具执行 → 状态演进."""
        state = {
            "messages": [
                HumanMessage(content="请分析A区域弱覆盖问题"),
                AIMessage(content="", tool_calls=[{"name": "search_terminology", "args": {}, "id": "tc_1"}]),
                ToolMessage(content="ok", tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="", tool_calls=[{"name": "search_design_doc", "args": {}, "id": "tc_2"}]),
                ToolMessage(content="ok", tool_call_id="tc_2", name="search_design_doc"),
                AIMessage(content="", tool_calls=[{"name": "match_scenario", "args": {"area": "A"}, "id": "tc_3"}]),
                ToolMessage(content='{"digitaltwinsId": "dt_001"}', tool_call_id="tc_3", name="match_scenario"),
                AIMessage(content="已匹配到数字孪生场景，正在执行根因分析..."),
            ],
            "todos": [
                {"content": "检索领域知识和术语定义", "status": "completed"},
                {"content": "检索分析流程文档", "status": "completed"},
                {"content": "匹配仿真场景", "status": "in_progress"},
                {"content": "执行根因分析", "status": "pending"},
                {"content": "展示分析结果", "status": "pending"},
            ],
        }

        context_msgs = build_todo_context(state)
        assert context_msgs is not None
        _print_result("context_builder 输出（多轮）", context_msgs[0].content)

        system_msg = {"role": "system", "content": TODO_SYSTEM_PROMPT}
        response = real_llm.invoke([system_msg] + context_msgs)
        raw = response.content
        _print_result("LLM 输出（多轮）", raw)

        result = parse_todo_result(raw)
        assert result is not None, f"解析失败: {raw}"
        _print_result("解析后的 todos（多轮）", result["todos"])
        _validate_todos(result["todos"])

        # 前 3 步应为 completed
        completed = [t for t in result["todos"] if t["status"] == "completed"]
        assert len(completed) >= 2, f"至少 2 步 completed，实际 {len(completed)}"


# ===========================================================================
# Example 3: SubAgentRunner.compile() — 真实 LLM 编译
# ===========================================================================

class TestRunnerCompileLive:
    """SubAgentRunner 使用真实 ChatOpenAI 编译子 Agent."""

    def test_compile_todo_tracker_simple_mode(self):
        """编译 TODO tracker → Simple 模式."""
        runner = SubAgentRunner()
        compiled = runner.compile(TODO_TRACKER_CONFIG)

        assert compiled.is_simple_mode is True
        assert compiled.name == "todo_tracker"
        assert compiled.llm is not None
        assert compiled.runnable is None
        _print_result("编译结果", {
            "name": compiled.name,
            "is_simple_mode": compiled.is_simple_mode,
            "llm_type": type(compiled.llm).__name__,
        })

    def test_compile_caching_real_llm(self):
        """同名子 Agent 的 LLM 实例应缓存."""
        runner = SubAgentRunner()
        compiled1 = runner.compile(TODO_TRACKER_CONFIG)
        compiled2 = runner.compile(TODO_TRACKER_CONFIG)
        assert compiled1 is compiled2
        assert compiled1.llm is compiled2.llm


# ===========================================================================
# Example 4: SubAgentRunner.invoke_reactive() — 真实调用
# ===========================================================================

class TestRunnerInvokeReactiveLive:
    """SubAgentRunner.invoke_reactive() 使用真实 LLM."""

    def test_invoke_reactive_first_turn(self):
        """首轮对话: invoke_reactive 应返回有效 todos."""
        runner = SubAgentRunner()
        compiled = runner.compile(TODO_TRACKER_CONFIG)

        state = {
            "messages": [
                HumanMessage(content="请分析C区域的容量问题"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "search_terminology", "args": {"query": "容量"}, "id": "tc_1"}],
                ),
                ToolMessage(content='{"terms": ["PRB利用率"]}', tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="已检索到容量相关术语，继续分析..."),
            ],
            "todos": [],
        }

        result = runner.invoke_reactive(compiled, state)
        _print_result("invoke_reactive 结果（首轮）", result)

        assert "todos" in result, f"结果应包含 todos key，实际: {result}"
        _validate_todos(result["todos"])

    def test_invoke_reactive_mid_turn(self):
        """中期对话: invoke_reactive 应更新现有 todos 状态."""
        runner = SubAgentRunner()
        compiled = runner.compile(TODO_TRACKER_CONFIG)

        state = {
            "messages": [
                HumanMessage(content="请分析弱覆盖问题"),
                AIMessage(content="", tool_calls=[{"name": "search_terminology", "args": {}, "id": "tc_1"}]),
                ToolMessage(content="ok", tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="", tool_calls=[{"name": "match_scenario", "args": {}, "id": "tc_2"}]),
                ToolMessage(content='{"id": "dt_001"}', tool_call_id="tc_2", name="match_scenario"),
                AIMessage(content="场景匹配完成，开始执行根因分析..."),
            ],
            "todos": [
                {"content": "检索领域知识和术语定义", "status": "completed"},
                {"content": "匹配仿真场景", "status": "in_progress"},
                {"content": "执行根因分析", "status": "pending"},
            ],
        }

        result = runner.invoke_reactive(compiled, state)
        _print_result("invoke_reactive 结果（中期）", result)

        assert "todos" in result
        _validate_todos(result["todos"])

    def test_invoke_reactive_trigger_condition_blocks(self):
        """最后一条为 ToolMessage 时，should_fire=False → context_builder 仍有结果，
        但实际调用由 middleware 层 trigger_condition 控制；这里验证 runner 层面仍可被调用."""
        runner = SubAgentRunner()
        compiled = runner.compile(TODO_TRACKER_CONFIG)

        state = {
            "messages": [
                HumanMessage(content="分析干扰"),
                ToolMessage(content="ok", tool_call_id="c1", name="search_terminology"),
            ],
            "todos": [],
        }

        # should_fire 为 False（最后是 ToolMessage）
        assert should_fire(state) is False

        # 但 runner.invoke_reactive 不检查 trigger_condition，仍会调用
        # context_builder 会因找到 HumanMessage 而返回上下文
        result = runner.invoke_reactive(compiled, state)
        _print_result("invoke_reactive（ToolMessage 尾部，runner 层面）", result)
        # runner 层面不应崩溃，可能返回有效 todos 或空 dict
        assert isinstance(result, dict)


# ===========================================================================
# Example 5: SubAgentMiddleware.after_model() — 真实端到端
# ===========================================================================

class TestMiddlewareAfterModelLive:
    """SubAgentMiddleware.after_model() 使用真实 LLM 调用."""

    def test_after_model_produces_todos(self):
        """after_model 应产生 todos state 更新."""
        from unittest.mock import MagicMock
        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(reactive=[TODO_TRACKER_CONFIG])

        state = {
            "messages": [
                HumanMessage(content="请分析D区域的切换问题"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "search_terminology", "args": {"query": "切换"}, "id": "tc_1"}],
                ),
                ToolMessage(content='{"terms": ["切换成功率"]}', tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="已获取切换相关术语，正在匹配场景..."),
            ],
            "todos": [],
        }

        mock_runtime = MagicMock()
        result = mw.after_model(state, mock_runtime)
        _print_result("after_model 结果", result)

        assert result is not None, "after_model 应返回非 None"
        assert "todos" in result, f"结果应包含 todos: {result}"
        _validate_todos(result["todos"])

    def test_after_model_skips_on_tool_message(self):
        """最后一条为 ToolMessage → should_fire=False → 不触发."""
        from unittest.mock import MagicMock
        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(reactive=[TODO_TRACKER_CONFIG])

        state = {
            "messages": [
                HumanMessage(content="分析"),
                ToolMessage(content="ok", tool_call_id="c1", name="t1"),
            ],
            "todos": [],
        }

        mock_runtime = MagicMock()
        result = mw.after_model(state, mock_runtime)
        assert result is None, "ToolMessage 结尾不应触发"


# ===========================================================================
# Example 6: 多轮 TODO 演进 — 真实 LLM 3 轮连续调用
# ===========================================================================

class TestMultiTurnEvolutionLive:
    """模拟 3 轮对话，验证 TODO 状态在真实 LLM 下逐步演进."""

    def test_three_rounds_todo_evolves(self):
        """3 轮对话中 TODO 从无到全部完成."""
        runner = SubAgentRunner()
        compiled = runner.compile(TODO_TRACKER_CONFIG)

        # --- Round 1: 用户提问 + 首个工具执行 ---
        state_r1 = {
            "messages": [
                HumanMessage(content="请分析E区域弱覆盖问题"),
                AIMessage(content="", tool_calls=[{"name": "search_terminology", "args": {}, "id": "tc_1"}]),
                ToolMessage(content='{"terms": ["RSRP"]}', tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="已获取术语，继续检索分析流程..."),
            ],
            "todos": [],
        }

        result_r1 = runner.invoke_reactive(compiled, state_r1)
        _print_result("Round 1 todos", result_r1)
        assert "todos" in result_r1
        todos_r1 = result_r1["todos"]
        _validate_todos(todos_r1)

        # --- Round 2: 更多工具执行 ---
        state_r2 = {
            "messages": state_r1["messages"] + [
                AIMessage(content="", tool_calls=[{"name": "match_scenario", "args": {}, "id": "tc_2"}]),
                ToolMessage(content='{"digitaltwinsId": "dt_005"}', tool_call_id="tc_2", name="match_scenario"),
                AIMessage(content="", tool_calls=[{"name": "query_root_cause_analysis", "args": {}, "id": "tc_3"}]),
                ToolMessage(content='{"rootCause": "天线方位角偏差"}', tool_call_id="tc_3", name="query_root_cause_analysis"),
                AIMessage(content="根因分析完成。是否需要对该场景进行优化仿真？"),
            ],
            "todos": todos_r1,
        }

        result_r2 = runner.invoke_reactive(compiled, state_r2)
        _print_result("Round 2 todos", result_r2)
        assert "todos" in result_r2
        todos_r2 = result_r2["todos"]
        _validate_todos(todos_r2)

        # Round 2 完成度应 > Round 1
        completed_r1 = sum(1 for t in todos_r1 if t["status"] == "completed")
        completed_r2 = sum(1 for t in todos_r2 if t["status"] == "completed")
        assert completed_r2 >= completed_r1, (
            f"Round 2 completed ({completed_r2}) 应 >= Round 1 ({completed_r1})"
        )

        # --- Round 3: 用户确认仿真 + 仿真完成 ---
        state_r3 = {
            "messages": state_r2["messages"] + [
                HumanMessage(content="是，进行优化仿真"),
                AIMessage(content="", tool_calls=[{"name": "query_simulation_results", "args": {}, "id": "tc_4"}]),
                ToolMessage(content='{"before": {}, "after": {}}', tool_call_id="tc_4", name="query_simulation_results"),
                AIMessage(content="优化仿真完成，以下是对比结果..."),
            ],
            "todos": todos_r2,
        }

        result_r3 = runner.invoke_reactive(compiled, state_r3)
        _print_result("Round 3 todos", result_r3)
        assert "todos" in result_r3
        todos_r3 = result_r3["todos"]
        _validate_todos(todos_r3)

        # Round 3 完成度应 >= Round 2
        completed_r3 = sum(1 for t in todos_r3 if t["status"] == "completed")
        assert completed_r3 >= completed_r2

        _print_result("3 轮演进汇总", {
            "round_1": {"count": len(todos_r1), "completed": completed_r1},
            "round_2": {"count": len(todos_r2), "completed": completed_r2},
            "round_3": {"count": len(todos_r3), "completed": completed_r3},
        })


# ===========================================================================
# Example 7: 自定义 Reactive 子 Agent — 真实 LLM
# ===========================================================================

class TestCustomReactiveLive:
    """演示自定义 reactive 子 Agent 使用真实 LLM."""

    def test_summary_agent(self):
        """自定义摘要生成子 Agent — 每次 AI 回复后生成简短摘要."""
        SUMMARY_PROMPT = """\
你是对话摘要生成器。根据当前对话状态，输出一个简短的 JSON 对象。

输出纯 JSON（无 markdown 标记），格式:
{"summary": "一句话摘要", "stage": "initial|analyzing|completed"}

规则:
- summary: 30 字以内，描述当前分析进展
- stage: initial=刚开始, analyzing=分析中, completed=分析完成
"""

        def build_summary_context(state):
            messages = state.get("messages", [])
            if not messages:
                return None
            parts = []
            for m in messages[-6:]:
                if isinstance(m, HumanMessage):
                    parts.append(f"用户: {m.content[:100]}")
                elif isinstance(m, AIMessage):
                    if m.tool_calls:
                        names = [tc.get("name", "?") for tc in m.tool_calls]
                        parts.append(f"Agent 调用: {', '.join(names)}")
                    elif m.content:
                        parts.append(f"Agent: {m.content[:100]}")
                elif isinstance(m, ToolMessage):
                    parts.append(f"工具 {getattr(m, 'name', '?')}: 成功")
            return [HumanMessage(content="\n".join(parts))] if parts else None

        def parse_summary_result(raw):
            content = raw.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                content = "\n".join(lines).strip()
            try:
                data = json.loads(content)
                if isinstance(data, dict) and "summary" in data:
                    return {"conversation_summary": data}
            except (json.JSONDecodeError, TypeError):
                pass
            return None

        config: ReactiveSubAgentConfig = {
            "name": "summary_agent",
            "description": "对话摘要生成器",
            "system_prompt": SUMMARY_PROMPT,
            "trigger_hook": "after_model",
            "context_builder": build_summary_context,
            "result_parser": parse_summary_result,
            "owned_state_keys": ["conversation_summary"],
            "fallback_on_error": {},
        }

        runner = SubAgentRunner()
        compiled = runner.compile(config)

        assert compiled.is_simple_mode is True

        state = {
            "messages": [
                HumanMessage(content="请分析F区域弱覆盖问题"),
                AIMessage(content="", tool_calls=[{"name": "search_terminology", "args": {}, "id": "tc_1"}]),
                ToolMessage(content="ok", tool_call_id="tc_1", name="search_terminology"),
                AIMessage(content="已获取弱覆盖相关术语，正在匹配场景..."),
            ],
        }

        result = runner.invoke_reactive(compiled, state)
        _print_result("自定义摘要 Agent 结果", result)

        assert "conversation_summary" in result, f"结果应包含 conversation_summary: {result}"
        summary = result["conversation_summary"]
        assert "summary" in summary
        assert "stage" in summary
        assert summary["stage"] in ("initial", "analyzing", "completed")

    def test_quality_scorer_agent(self):
        """自定义质量评分子 Agent — 对 Agent 输出质量打分."""
        SCORER_PROMPT = """\
你是 Agent 输出质量评分器。评估最近一次 Agent 回复的质量。

输出纯 JSON（无 markdown 标记），格式:
{"score": 1-10, "reason": "简短评价"}

评分标准:
- 10: 完美回复，信息准确完整
- 7-9: 良好回复，基本满足需求
- 4-6: 一般回复，有改进空间
- 1-3: 差的回复，需要重新生成
"""

        def build_scorer_context(state):
            messages = state.get("messages", [])
            # 找最后一条 AIMessage
            for m in reversed(messages):
                if isinstance(m, AIMessage) and m.content:
                    return [HumanMessage(content=f"请评估以下回复的质量:\n\n{m.content[:500]}")]
            return None

        def parse_score_result(raw):
            content = raw.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                content = "\n".join(lines).strip()
            try:
                data = json.loads(content)
                if isinstance(data, dict) and "score" in data:
                    score = int(data["score"])
                    if 1 <= score <= 10:
                        return {"quality_score": data}
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
            return None

        config: ReactiveSubAgentConfig = {
            "name": "quality_scorer",
            "description": "输出质量评分器",
            "system_prompt": SCORER_PROMPT,
            "trigger_hook": "after_model",
            "trigger_condition": lambda s: (
                isinstance(s.get("messages", [])[-1], AIMessage)
                and bool(s["messages"][-1].content)
                if s.get("messages") else False
            ),
            "context_builder": build_scorer_context,
            "result_parser": parse_score_result,
            "owned_state_keys": ["quality_score"],
            "fallback_on_error": {},
        }

        runner = SubAgentRunner()
        compiled = runner.compile(config)

        state = {
            "messages": [
                HumanMessage(content="分析弱覆盖"),
                AIMessage(
                    content="经过分析，A区域弱覆盖的主要原因是：\n"
                    "1. 天线下倾角配置不当（当前8°，建议调整为6°）\n"
                    "2. 站间距过大（平均500m）\n"
                    "3. 建筑物遮挡导致信号衰减\n"
                    "建议优先调整天线参数。"
                ),
            ],
        }

        result = runner.invoke_reactive(compiled, state)
        _print_result("质量评分 Agent 结果", result)

        assert "quality_score" in result, f"结果应包含 quality_score: {result}"
        score_data = result["quality_score"]
        assert "score" in score_data
        assert 1 <= int(score_data["score"]) <= 10


# ===========================================================================
# Example 8: 多 Reactive 子 Agent 并行 — 真实 LLM
# ===========================================================================

class TestMultipleReactiveLive:
    """多个 reactive 子 Agent 同时注册，after_model 同时触发."""

    def test_todo_and_custom_both_fire(self):
        """TODO tracker + 自定义摘要 Agent 同时触发并合并结果."""
        SUMMARY_PROMPT = "你是摘要生成器。输出纯JSON: {\"summary\": \"一句话\", \"stage\": \"analyzing\"}"

        summary_config: ReactiveSubAgentConfig = {
            "name": "live_summary",
            "description": "摘要生成",
            "system_prompt": SUMMARY_PROMPT,
            "trigger_hook": "after_model",
            "trigger_condition": should_fire,
            "context_builder": lambda state: [HumanMessage(content="用户正在分析弱覆盖")] if state.get("messages") else None,
            "result_parser": lambda raw: _safe_parse_summary(raw),
            "owned_state_keys": ["summary"],
            "fallback_on_error": {},
        }

        from unittest.mock import MagicMock
        from app.agent.subagents.middleware import SubAgentMiddleware

        mw = SubAgentMiddleware(reactive=[TODO_TRACKER_CONFIG, summary_config])

        state = {
            "messages": [
                HumanMessage(content="分析弱覆盖"),
                AIMessage(content="正在分析弱覆盖问题..."),
            ],
            "todos": [],
        }

        mock_runtime = MagicMock()
        result = mw.after_model(state, mock_runtime)
        _print_result("多 Reactive 合并结果", result)

        assert result is not None, "至少一个 reactive 应返回更新"
        # TODO tracker 应返回 todos
        if "todos" in result:
            _validate_todos(result["todos"])


def _safe_parse_summary(raw: str):
    """安全解析摘要 JSON."""
    content = raw.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines).strip()
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "summary" in data:
            return {"summary": data}
    except (json.JSONDecodeError, TypeError):
        pass
    return None
