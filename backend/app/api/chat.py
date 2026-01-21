"""
聊天 API 路由
"""

import uuid
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
import json

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    TodoStep,
    TaskStatus,
    PendingConfig,
)
from app.agents import get_agent_graph, AgentState
from app.tools import get_default_tools


def serialize_state_for_sse(state_data: dict) -> dict:
    """
    将 state 数据序列化为可 JSON 编码的格式
    处理 TypedDict 和其他特殊类型
    """
    serialized = {}

    # 处理 pending_config
    if "pending_config" in state_data and state_data["pending_config"]:
        pc = state_data["pending_config"]
        serialized["pending_config"] = {
            "step_id": pc.get("step_id"),
            "title": pc.get("title"),
            "description": pc.get("description"),
            "fields": [
                {
                    "name": f.get("name"),
                    "label": f.get("label"),
                    "field_type": f.get("field_type"),
                    "required": f.get("required", False),
                    "default": f.get("default"),
                    "options": f.get("options"),
                    "placeholder": f.get("placeholder"),
                    "description": f.get("description"),
                }
                for f in pc.get("fields", [])
            ],
            "values": pc.get("values", {}),
        }

    # 处理 todo_list
    if "todo_list" in state_data:
        serialized["todo_list"] = state_data["todo_list"]

    return serialized

router = APIRouter()


def state_to_response(state: dict, thread_id: str) -> ChatResponse:
    """将 Agent State 转换为 API 响应"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None

    # 转换 todo_list
    todo_list = []
    for step in state.get("todo_list", []):
        todo_list.append(
            TodoStep(
                id=step["id"],
                description=step["description"],
                tool_name=step.get("tool_name"),
                status=step["status"],
                result=step.get("result"),
                error=step.get("error"),
                depends_on=step.get("depends_on", []),
                progress=step.get("progress", 0),
            )
        )

    # 转换 pending_config
    pending_config = None
    if state.get("pending_config"):
        pc = state["pending_config"]
        pending_config = PendingConfig(
            step_id=pc["step_id"],
            title=pc["title"],
            description=pc.get("description"),
            fields=pc.get("fields", []),
            values=pc.get("values", {}),
        )

    # 构建响应消息
    response_message = ChatMessage(
        role="assistant",
        content=last_message.content if last_message else "正在处理...",
    )

    # 映射状态
    status_map = {
        "pending": TaskStatus.PENDING,
        "running": TaskStatus.RUNNING,
        "success": TaskStatus.SUCCESS,
        "failed": TaskStatus.FAILED,
        "waiting_input": TaskStatus.WAITING_INPUT,
    }
    task_status = status_map.get(
        state.get("final_status", "pending"), TaskStatus.PENDING
    )

    return ChatResponse(
        thread_id=thread_id,
        message=response_message,
        todo_list=todo_list,
        pending_config=pending_config,
        task_status=task_status,
    )


@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """发送聊天消息"""
    # 获取或创建 thread_id
    thread_id = request.thread_id or str(uuid.uuid4())

    # 获取 Agent Graph
    tools = get_default_tools()
    graph = get_agent_graph(tools)

    config = {"configurable": {"thread_id": thread_id}}

    # 检查是否是配置响应
    if request.config_response:
        # 恢复被中断的执行
        result = graph.invoke(
            Command(resume=request.config_response),
            config=config,
        )
    else:
        # 新消息
        result = graph.invoke(
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
        )

    return state_to_response(result, thread_id)


@router.post("/stream")
async def stream_message(request: ChatRequest):
    """流式发送聊天消息"""
    thread_id = request.thread_id or str(uuid.uuid4())

    tools = get_default_tools()
    graph = get_agent_graph(tools)

    config = {"configurable": {"thread_id": thread_id}}

    async def generate() -> AsyncGenerator[str, None]:
        """生成 SSE 事件流"""
        try:
            if request.config_response:
                stream = graph.stream(
                    Command(resume=request.config_response),
                    config=config,
                    stream_mode="updates",
                )
            else:
                stream = graph.stream(
                    {"messages": [HumanMessage(content=request.message)]},
                    config=config,
                    stream_mode="updates",
                )

            has_interrupt = False
            for update in stream:
                # 发送更新事件
                event_data = {
                    "type": "update",
                    "thread_id": thread_id,
                    "data": {},
                }

                # 提取节点更新
                for node_name, node_state in update.items():
                    if node_name == "__interrupt__":
                        # 检测到中断
                        has_interrupt = True
                        continue
                    else:
                        event_data["data"]["node"] = node_name
                        if "messages" in node_state:
                            msgs = node_state["messages"]
                            if msgs:
                                last_msg = msgs[-1]
                                event_data["data"]["content"] = last_msg.content
                        if "todo_list" in node_state:
                            event_data["data"]["todo_list"] = node_state["todo_list"]
                        if "final_status" in node_state:
                            event_data["data"]["status"] = node_state["final_status"]
                        if "pending_config" in node_state and node_state["pending_config"]:
                            # 序列化 pending_config
                            serialized = serialize_state_for_sse({"pending_config": node_state["pending_config"]})
                            if "pending_config" in serialized:
                                event_data["data"]["pending_config"] = serialized["pending_config"]

                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            # 如果发生中断，获取最新状态并发送 interrupt 事件
            if has_interrupt:
                final_state = graph.get_state(config)
                if final_state and final_state.values:
                    # 使用序列化函数处理 state 数据
                    serialized_data = serialize_state_for_sse(final_state.values)
                    interrupt_event = {
                        "type": "interrupt",
                        "thread_id": thread_id,
                        "data": serialized_data,
                    }
                    yield f"data: {json.dumps(interrupt_event, ensure_ascii=False)}\n\n"
            else:
                # 正常完成，发送完成事件
                yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id})}\n\n"

        except Exception as e:
            error_event = {
                "type": "error",
                "thread_id": thread_id,
                "error": str(e),
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

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
async def get_chat_state(thread_id: str):
    """获取会话状态"""
    graph = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = graph.get_state(config)
        if state and state.values:
            return state_to_response(state.values, thread_id)
        raise HTTPException(status_code=404, detail="会话不存在")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume/{thread_id}")
async def resume_chat(thread_id: str, config_values: dict):
    """恢复被中断的会话"""
    graph = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # 更新状态
        graph.update_state(config, {"pending_config": None})

        # 继续执行
        result = graph.invoke(
            Command(resume=config_values),
            config=config,
        )

        return state_to_response(result, thread_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
