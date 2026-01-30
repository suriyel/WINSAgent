"""Tests for TODO Tracker reactive sub-agent.

验证:
- build_todo_context: 不同 state 形态下的上下文提取
- parse_todo_result: JSON 解析、markdown 去除、规范化、边界情况
- should_fire: 触发条件判定
- TODO_TRACKER_CONFIG: 完整配置结构
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.subagents.agents.todo_tracker import (
    TODO_TRACKER_CONFIG,
    build_todo_context,
    parse_todo_result,
    should_fire,
)


# ===========================================================================
# build_todo_context 测试
# ===========================================================================


class TestBuildTodoContext:
    """Context builder: 从 parent state 提取精简上下文."""

    # --- Example 1: 空 state ---
    def test_empty_state_returns_none(self):
        """空 messages 应返回 None."""
        assert build_todo_context({"messages": []}) is None
        assert build_todo_context({}) is None

    # --- Example 2: 仅有用户消息 ---
    def test_with_only_user_message(self):
        """仅含用户消息时应提取用户任务."""
        state = {
            "messages": [HumanMessage(content="请分析弱覆盖问题")],
            "todos": [],
        }
        result = build_todo_context(state)
        assert result is not None
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert "请分析弱覆盖问题" in result[0].content

    # --- Example 3: 多轮对话含工具调用 ---
    def test_multi_turn_with_tool_calls(self, multi_turn_state):
        """多轮对话应提取用户任务 + 当前 todos + 最近操作."""
        result = build_todo_context(multi_turn_state)
        assert result is not None
        content = result[0].content

        # 包含用户任务
        assert "请分析A区域弱覆盖问题" in content
        # 包含当前步骤
        assert "检索领域知识" in content
        assert "匹配仿真场景" in content
        # 包含最近操作
        assert "search_terminology" in content or "调用工具" in content

    # --- Example 4: 没有 todos 时提示创建 ---
    def test_no_todos_shows_create_hint(self):
        """无 todos 时应提示创建初始步骤."""
        state = {
            "messages": [HumanMessage(content="分析干扰问题")],
            "todos": [],
        }
        result = build_todo_context(state)
        content = result[0].content
        assert "创建初始步骤" in content

    # --- Example 5: 长消息截断 ---
    def test_long_user_message_truncation(self):
        """超长用户消息应截断到 300 字符."""
        long_text = "分析" * 200  # 400 字符
        state = {
            "messages": [HumanMessage(content=long_text)],
            "todos": [],
        }
        result = build_todo_context(state)
        content = result[0].content
        # 用户任务部分应被截断
        task_line = content.split("\n")[0]  # "用户任务: ..."
        task_content = task_line.replace("用户任务: ", "")
        assert len(task_content) <= 300

    # --- Example 6: 仅有非 HumanMessage 消息 ---
    def test_no_human_message_returns_none(self):
        """仅有 AI/Tool 消息、无 HumanMessage 时应返回 None."""
        state = {
            "messages": [
                AIMessage(content="分析结果如下..."),
                ToolMessage(content="ok", tool_call_id="c1", name="tool1"),
            ],
        }
        assert build_todo_context(state) is None

    # --- Example 7: 工具结果状态提取 ---
    def test_tool_result_status_extraction(self):
        """应正确提取工具成功/失败状态."""
        state = {
            "messages": [
                HumanMessage(content="测试"),
                ToolMessage(content="ok", tool_call_id="c1", name="search_terminology"),
                ToolMessage(content="error", tool_call_id="c2", name="match_scenario", status="error"),
            ],
            "todos": [],
        }
        result = build_todo_context(state)
        content = result[0].content
        assert "search_terminology" in content
        assert "match_scenario" in content


# ===========================================================================
# parse_todo_result 测试
# ===========================================================================


class TestParseTodoResult:
    """Result parser: 解析 LLM JSON 输出."""

    # --- Example 1: 标准 JSON 数组 ---
    def test_valid_json_array(self):
        """标准 JSON 数组应正确解析."""
        raw = json.dumps([
            {"content": "检索领域知识", "status": "completed"},
            {"content": "匹配仿真场景", "status": "in_progress"},
            {"content": "执行根因分析", "status": "pending"},
        ])
        result = parse_todo_result(raw)
        assert result is not None
        assert "todos" in result
        assert len(result["todos"]) == 3
        assert result["todos"][0] == {"content": "检索领域知识", "status": "completed"}
        assert result["todos"][1] == {"content": "匹配仿真场景", "status": "in_progress"}
        assert result["todos"][2] == {"content": "执行根因分析", "status": "pending"}

    # --- Example 2: Markdown 包裹的 JSON ---
    def test_markdown_wrapped_json(self):
        """被 ```json ... ``` 包裹的内容应正确去除标记后解析."""
        raw = '```json\n[{"content": "步骤1", "status": "completed"}]\n```'
        result = parse_todo_result(raw)
        assert result is not None
        assert len(result["todos"]) == 1
        assert result["todos"][0]["content"] == "步骤1"

    # --- Example 3: 普通 ``` 包裹 ---
    def test_plain_code_fence(self):
        """被普通 ``` 包裹的内容也应能解析."""
        raw = '```\n[{"content": "A", "status": "pending"}]\n```'
        result = parse_todo_result(raw)
        assert result is not None
        assert result["todos"][0]["content"] == "A"

    # --- Example 4: 无效 JSON ---
    def test_invalid_json_returns_none(self):
        """无效 JSON 应返回 None."""
        assert parse_todo_result("这不是JSON") is None
        assert parse_todo_result("{invalid}") is None
        assert parse_todo_result("") is None
        assert parse_todo_result(None) is None

    # --- Example 5: 非数组 JSON ---
    def test_non_array_json_returns_none(self):
        """JSON 对象（非数组）应返回 None."""
        assert parse_todo_result('{"content": "步骤1"}') is None
        assert parse_todo_result('"just a string"') is None

    # --- Example 6: 无效 status 值自动修正 ---
    def test_invalid_status_normalized_to_pending(self):
        """未知 status 值应修正为 pending."""
        raw = json.dumps([
            {"content": "步骤1", "status": "running"},   # 无效
            {"content": "步骤2", "status": "done"},       # 无效
            {"content": "步骤3", "status": "completed"},  # 有效
        ])
        result = parse_todo_result(raw)
        assert result["todos"][0]["status"] == "pending"
        assert result["todos"][1]["status"] == "pending"
        assert result["todos"][2]["status"] == "completed"

    # --- Example 7: 空 content 的条目被过滤 ---
    def test_empty_content_filtered(self):
        """content 为空的条目应被过滤."""
        raw = json.dumps([
            {"content": "", "status": "pending"},
            {"content": "有效步骤", "status": "completed"},
            {"content": "  ", "status": "pending"},  # 空白也被过滤
        ])
        result = parse_todo_result(raw)
        assert len(result["todos"]) == 1
        assert result["todos"][0]["content"] == "有效步骤"

    # --- Example 8: 混合有效/无效条目 ---
    def test_mixed_valid_invalid_items(self):
        """非 dict 条目应被过滤."""
        raw = json.dumps([
            {"content": "步骤1", "status": "completed"},
            "这不是dict",
            42,
            {"content": "步骤2", "status": "pending"},
        ])
        result = parse_todo_result(raw)
        assert len(result["todos"]) == 2

    # --- Example 9: 全部无效时返回 None ---
    def test_all_invalid_returns_none(self):
        """所有条目都无效时应返回 None."""
        raw = json.dumps([
            {"content": "", "status": "pending"},
            "not a dict",
        ])
        assert parse_todo_result(raw) is None

    # --- Example 10: 带额外空白的输入 ---
    def test_whitespace_handling(self):
        """输入前后的空白应被正确处理."""
        raw = '\n  [{"content": "步骤1", "status": "pending"}]  \n'
        result = parse_todo_result(raw)
        assert result is not None
        assert len(result["todos"]) == 1


# ===========================================================================
# should_fire 测试
# ===========================================================================


class TestShouldFire:
    """Trigger condition: 仅在最后一条为 AIMessage 时触发."""

    # --- Example 1: 最后是 AIMessage ---
    def test_fires_on_ai_message(self):
        """最后一条为 AIMessage 时应触发."""
        state = {"messages": [HumanMessage(content="hi"), AIMessage(content="回复")]}
        assert should_fire(state) is True

    # --- Example 2: 最后是 HumanMessage ---
    def test_skips_human_message(self):
        """最后一条为 HumanMessage 时不应触发."""
        state = {"messages": [AIMessage(content="a"), HumanMessage(content="b")]}
        assert should_fire(state) is False

    # --- Example 3: 最后是 ToolMessage ---
    def test_skips_tool_message(self):
        """最后一条为 ToolMessage 时不应触发."""
        state = {"messages": [ToolMessage(content="ok", tool_call_id="c1", name="t1")]}
        assert should_fire(state) is False

    # --- Example 4: 空消息列表 ---
    def test_empty_messages(self):
        """空消息列表不触发."""
        assert should_fire({"messages": []}) is False
        assert should_fire({}) is False

    # --- Example 5: 单条 AIMessage ---
    def test_single_ai_message(self):
        """仅一条 AIMessage 也应触发."""
        state = {"messages": [AIMessage(content="你好")]}
        assert should_fire(state) is True


# ===========================================================================
# TODO_TRACKER_CONFIG 完整配置测试
# ===========================================================================


class TestTodoTrackerConfig:
    """验证导出的 TODO_TRACKER_CONFIG 配置完整性."""

    def test_required_fields_present(self):
        """所有必填字段应存在."""
        cfg = TODO_TRACKER_CONFIG
        assert "name" in cfg
        assert "description" in cfg
        assert "system_prompt" in cfg
        assert "trigger_hook" in cfg
        assert "context_builder" in cfg
        assert "owned_state_keys" in cfg

    def test_system_prompt_is_chinese(self):
        """系统提示词应为中文."""
        assert "任务进度跟踪器" in TODO_TRACKER_CONFIG["system_prompt"]
        assert "JSON" in TODO_TRACKER_CONFIG["system_prompt"]

    def test_owned_state_keys(self):
        """应管理 todos key."""
        assert TODO_TRACKER_CONFIG["owned_state_keys"] == ["todos"]

    def test_is_simple_mode_config(self):
        """应为 Simple 模式（无 tools）."""
        tools = TODO_TRACKER_CONFIG.get("tools")
        assert tools is None or len(tools) == 0
