"""
聊天 API 路由 (v2)

基于 LangGraph create_react_agent 的新架构:
- 使用 astream_events 进行流式输出
- 使用原生 interrupt() 处理 HITL
- 使用 Command(resume=) 恢复中断
"""

import json
import uuid
from datetime import datetime
from typing import AsyncGenerator, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from app.agents import get_agent, get_agent_state
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    TodoStep,
    TaskStatus,
    PendingConfig,
    ResumeRequest,
)
from app.api.conversations import _conversations_store, ConversationInfo

router = APIRouter()


# ============== 辅助函数 ==============


def create_or_update_conversation(thread_id: str, message: str | None = None):
    """创建或更新对话记录"""
    try:
        if thread_id in _conversations_store:
            conv = _conversations_store[thread_id]
            if message:
                conv.title = message[:30]
                conv.last_message = message[:100]
            conv.updated_at = datetime.now()
        else:
            _conversations_store[thread_id] = ConversationInfo(
                thread_id=thread_id,
                title=message[:30] if message else "新对话",
                last_message=message[:100] if message else None,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
    except Exception as e:
        print(f"[WARN] Failed to create/update conversation: {e}")


def format_sse_event(event_type: str, data: dict) -> str:
    """格式化 SSE 事件"""
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


def extract_todo_list_from_store(agent, thread_id: str) -> list[dict] | None:
    """从 Store 中提取 todo_list"""
    try:
        from app.agents import get_store
        store = get_store()
        result = store.get(("todos",), thread_id)
        if result and result.value:
            todo_data = result.value
            return [
                {
                    "id": step.get("id", str(i)),
                    "description": step.get("description", ""),
                    "status": step.get("status", "pending"),
                    "result": step.get("result"),
                    "error": step.get("error"),
                }
                for i, step in enumerate(todo_data.get("steps", []))
            ]
    except Exception as e:
        print(f"[WARN] Failed to extract todo_list: {e}")
    return None


def state_to_response(state: dict, thread_id: str) -> ChatResponse:
    """将 Agent State 转换为 API 响应"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None

    # 获取 todo_list
    todo_list = []
    # 先尝试从 store 获取
    from app.agents import get_agent
    agent = get_agent()
    store_todos = extract_todo_list_from_store(agent, thread_id)
    if store_todos:
        for step in store_todos:
            todo_list.append(
                TodoStep(
                    id=step.get("id", ""),
                    description=step.get("description", ""),
                    tool_name=step.get("tool_name"),
                    status=step.get("status", "pending"),
                    result=step.get("result"),
                    error=step.get("error"),
                    depends_on=[],
                    progress=100 if step.get("status") == "completed" else 0,
                )
            )

    # 转换消息历史
    chat_messages = []
    for msg in messages:
        if hasattr(msg, "type"):
            msg_type = msg.type
        else:
            msg_type = getattr(msg, "role", "assistant")

        # 跳过工具消息和空消息
        if msg_type == "tool":
            continue
        content = getattr(msg, "content", "") or ""
        if not content or content.isspace():
            continue

        role_map = {"human": "user", "ai": "assistant", "system": "system"}
        role = role_map.get(msg_type, "assistant")

        chat_messages.append(
            ChatMessage(
                role=role,
                content=content,
                timestamp=datetime.now(),
            )
        )

    # 响应消息
    response_content = ""
    if last_message:
        response_content = getattr(last_message, "content", "") or "处理完成"

    response_message = ChatMessage(
        role="assistant",
        content=response_content,
    )

    return ChatResponse(
        thread_id=thread_id,
        message=response_message,
        messages=chat_messages,
        todo_list=todo_list,
        pending_config=None,
        task_status=TaskStatus.SUCCESS,
    )


# ============== API 端点 ==============


@router.post("/stream")
async def stream_message(request: ChatRequest):
    """
    流式发送聊天消息

    使用 LangGraph astream_events 进行流式输出，支持:
    - 实时 token 输出
    - 工具调用状态
    - HITL 中断
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    create_or_update_conversation(thread_id, request.message)

    agent = get_agent()
    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": "default",
        }
    }

    async def generate() -> AsyncGenerator[str, None]:
        """生成 SSE 事件流"""
        try:
            accumulated_content = ""
            current_tool = None
            has_interrupt = False

            # 使用 astream_events 进行流式处理
            async for event in agent.astream_events(
                {"messages": [{"role": "user", "content": request.message}]},
                config=config,
                version="v2",
            ):
                event_kind = event.get("event", "")

                # 处理 LLM 流式输出
                if event_kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        accumulated_content += chunk.content
                        yield format_sse_event("update", {
                            "thread_id": thread_id,
                            "data": {
                                "content": chunk.content,
                                "accumulated": accumulated_content,
                            }
                        })

                # 处理工具调用开始
                elif event_kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})
                    current_tool = tool_name
                    yield format_sse_event("update", {
                        "thread_id": thread_id,
                        "data": {
                            "node": "tool",
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                            "status": "running",
                        }
                    })

                # 处理工具调用结束
                elif event_kind == "on_tool_end":
                    tool_name = event.get("name", current_tool or "unknown")
                    tool_output = event.get("data", {}).get("output", "")
                    yield format_sse_event("update", {
                        "thread_id": thread_id,
                        "data": {
                            "node": "tool",
                            "tool_name": tool_name,
                            "tool_output": str(tool_output)[:500],
                            "status": "completed",
                        }
                    })
                    current_tool = None

            # 检查是否有中断 (HITL)
            state = agent.get_state(config)
            if state and state.tasks:
                # 有待处理的中断
                for task in state.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        interrupt_data = task.interrupts[0].value
                        has_interrupt = True

                        # 构建 pending_config
                        pending_config = {
                            "step_id": interrupt_data.get("tool_name", "unknown"),
                            "title": interrupt_data.get("action", "需要确认"),
                            "description": interrupt_data.get("reason", ""),
                            "interrupt_type": interrupt_data.get("type", "authorization"),
                            "tool_name": interrupt_data.get("tool_name"),
                            "tool_args": interrupt_data.get("params", {}),
                            "fields": [],
                            "values": interrupt_data.get("params", {}),
                        }

                        # 根据中断类型添加字段
                        if interrupt_data.get("type") == "input_required":
                            pending_config["fields"] = [{
                                "name": "input",
                                "label": interrupt_data.get("question", "请输入"),
                                "field_type": "text",
                                "required": True,
                            }]
                        elif interrupt_data.get("choices"):
                            pending_config["fields"] = [{
                                "name": "choice",
                                "label": interrupt_data.get("question", "请选择"),
                                "field_type": "select",
                                "required": True,
                                "options": interrupt_data.get("choices", []),
                            }]

                        yield format_sse_event("interrupt", {
                            "thread_id": thread_id,
                            "data": {
                                "pending_config": pending_config,
                            }
                        })
                        break

            if not has_interrupt:
                # 正常完成
                # 获取 todo_list
                todo_list = extract_todo_list_from_store(agent, thread_id)

                done_data: dict[str, Any] = {
                    "thread_id": thread_id,
                    "data": {"status": "completed"},
                }
                if todo_list:
                    done_data["data"]["todo_list"] = todo_list

                yield format_sse_event("done", done_data)

                # 更新对话
                if accumulated_content:
                    create_or_update_conversation(thread_id, accumulated_content)

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield format_sse_event("error", {
                "thread_id": thread_id,
                "error": str(e),
            })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/resume/{thread_id}")
async def resume_chat(thread_id: str, request: ResumeRequest):
    """
    恢复被中断的会话

    使用 LangGraph Command(resume=) 恢复执行。

    支持的 action:
    - approve: 批准执行
    - reject: 拒绝执行
    - edit: 修改参数后执行
    - confirm: 确认输入
    - cancel: 取消操作
    """
    agent = get_agent()
    config = {"configurable": {"thread_id": thread_id}}

    # 解析 action
    action = request.action or request.dict().get("_action")
    if not action:
        raise HTTPException(status_code=400, detail="Missing action field")

    # 构建恢复数据
    resume_data: dict[str, Any] = {"action": action}

    # 处理不同的 action
    if action in ("reject", "cancel"):
        resume_data["reason"] = request.reason or "用户取消"

    elif action == "edit":
        # 使用修改后的参数
        resume_data["params"] = request.values or {}

    elif action == "confirm":
        # 用户输入
        resume_data["input"] = request.values.get("input", "") if request.values else ""

    elif action == "approve":
        # 批准，无需额外数据
        pass

    async def generate() -> AsyncGenerator[str, None]:
        """生成 SSE 事件流"""
        try:
            accumulated_content = ""
            has_interrupt = False

            # 使用 Command(resume=) 恢复执行
            async for event in agent.astream_events(
                Command(resume=resume_data),
                config=config,
                version="v2",
            ):
                event_kind = event.get("event", "")

                if event_kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        accumulated_content += chunk.content
                        yield format_sse_event("update", {
                            "thread_id": thread_id,
                            "data": {"content": chunk.content}
                        })

                elif event_kind == "on_tool_start":
                    yield format_sse_event("update", {
                        "thread_id": thread_id,
                        "data": {
                            "node": "tool",
                            "tool_name": event.get("name"),
                            "status": "running",
                        }
                    })

                elif event_kind == "on_tool_end":
                    yield format_sse_event("update", {
                        "thread_id": thread_id,
                        "data": {
                            "node": "tool",
                            "tool_name": event.get("name"),
                            "status": "completed",
                        }
                    })

            # 检查是否还有中断
            state = agent.get_state(config)
            if state and state.tasks:
                for task in state.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        interrupt_data = task.interrupts[0].value
                        has_interrupt = True
                        yield format_sse_event("interrupt", {
                            "thread_id": thread_id,
                            "data": {
                                "pending_config": {
                                    "step_id": interrupt_data.get("tool_name", "unknown"),
                                    "title": interrupt_data.get("action", "需要确认"),
                                    "interrupt_type": interrupt_data.get("type", "authorization"),
                                    "tool_name": interrupt_data.get("tool_name"),
                                    "tool_args": interrupt_data.get("params", {}),
                                    "fields": [],
                                    "values": {},
                                }
                            }
                        })
                        break

            if not has_interrupt:
                todo_list = extract_todo_list_from_store(agent, thread_id)
                done_data: dict[str, Any] = {
                    "thread_id": thread_id,
                    "data": {"status": "completed"},
                }
                if todo_list:
                    done_data["data"]["todo_list"] = todo_list
                yield format_sse_event("done", done_data)

                if accumulated_content:
                    create_or_update_conversation(thread_id, accumulated_content)

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield format_sse_event("error", {
                "thread_id": thread_id,
                "error": str(e),
            })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/state/{thread_id}")
async def get_chat_state_endpoint(thread_id: str):
    """获取会话状态"""
    agent = get_agent()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = agent.get_state(config)
        if state and state.values:
            return state_to_response(state.values, thread_id)
        raise HTTPException(status_code=404, detail="会话不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== 向后兼容端点 ==============


@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    [Deprecated] 同步发送消息

    推荐使用 /stream 端点
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    create_or_update_conversation(thread_id, request.message)

    agent = get_agent()
    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": "default",
        }
    }

    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": request.message}]},
            config=config,
        )
        return state_to_response(result, thread_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
