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
from app.agents.hitl import HITLAction, HITLMessageEncoder
from app.tools import get_default_tools


def serialize_state_for_sse(state_data: dict) -> dict:
    """
    将 state 数据序列化为可 JSON 编码的格式
    处理 TypedDict 和其他特殊类型
    """
    print(f"[SERIALIZE] Input state_data keys: {state_data.keys()}")
    print(f"[SERIALIZE] pending_config exists: {'pending_config' in state_data}")
    print(f"[SERIALIZE] pending_config value: {state_data.get('pending_config')}")

    serialized = {}

    # 处理 pending_config
    if "pending_config" in state_data and state_data["pending_config"]:
        pc = state_data["pending_config"]
        print(f"[SERIALIZE] Processing pending_config: {pc}")
        print(f"[SERIALIZE] PC type: {type(pc)}")
        print(f"[SERIALIZE] PC fields: {pc.get('fields') if hasattr(pc, 'get') else 'not dict-like'}")

        def serialize_field(f):
            """递归序列化字段（支持嵌套和数组类型）"""
            result = {
                "name": f.get("name"),
                "label": f.get("label"),
                "field_type": f.get("field_type"),
                "required": f.get("required", False),
                "default": f.get("default"),
                "options": f.get("options"),
                "placeholder": f.get("placeholder"),
                "description": f.get("description"),
                "children": None,
                "item_type": None,
            }
            # 递归处理 children (object 类型)
            if f.get("children"):
                result["children"] = [serialize_field(c) for c in f["children"]]
            # 递归处理 item_type (array 类型)
            if f.get("item_type"):
                result["item_type"] = serialize_field(f["item_type"])
            return result

        serialized["pending_config"] = {
            "step_id": pc.get("step_id"),
            "title": pc.get("title"),
            "description": pc.get("description"),
            "fields": [serialize_field(f) for f in pc.get("fields", [])],
            "values": pc.get("values", {}),
            # 新增字段
            "interrupt_type": pc.get("interrupt_type", "authorization"),
            "tool_name": pc.get("tool_name"),
            "tool_args": pc.get("tool_args"),
        }
        print(f"[SERIALIZE] Serialized pending_config: {serialized['pending_config']}")
    else:
        print(f"[SERIALIZE] No pending_config to serialize")

    # 处理 todo_list
    if "todo_list" in state_data:
        serialized["todo_list"] = state_data["todo_list"]
        print(f"[SERIALIZE] Added todo_list with {len(state_data['todo_list'])} items")

    print(f"[SERIALIZE] Final serialized keys: {serialized.keys()}")
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
            interrupt_type=pc.get("interrupt_type", "authorization"),
            tool_name=pc.get("tool_name"),
            tool_args=pc.get("tool_args"),
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

            needs_user_input = False
            last_state_data = {}

            for update in stream:
                # 发送更新事件
                event_data = {
                    "type": "update",
                    "thread_id": thread_id,
                    "data": {},
                }

                # 提取节点更新
                for node_name, node_state in update.items():
                    event_data["data"]["node"] = node_name

                    # 保存最新的 state 数据
                    last_state_data = node_state

                    if "messages" in node_state:
                        msgs = node_state["messages"]
                        if msgs:
                            last_msg = msgs[-1]
                            event_data["data"]["content"] = last_msg.content

                    if "todo_list" in node_state:
                        event_data["data"]["todo_list"] = node_state["todo_list"]

                    if "final_status" in node_state:
                        event_data["data"]["status"] = node_state["final_status"]
                        # 检测是否需要用户输入
                        if node_state["final_status"] == "waiting_input":
                            needs_user_input = True
                            print(f"[DEBUG] Detected waiting_input status in node: {node_name}")

                    if "pending_config" in node_state and node_state["pending_config"]:
                        print(f"[DEBUG] Found pending_config in node {node_name}: {node_state['pending_config']}")
                        # 序列化 pending_config
                        serialized = serialize_state_for_sse({"pending_config": node_state["pending_config"]})
                        if "pending_config" in serialized:
                            event_data["data"]["pending_config"] = serialized["pending_config"]
                            print(f"[DEBUG] Serialized and added to event: {serialized['pending_config']}")

                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            # 如果需要用户输入，发送 interrupt 事件
            if needs_user_input:
                print(f"[DEBUG] Stream ended with waiting_input status, sending interrupt event")
                print(f"[DEBUG] Last state data keys: {last_state_data.keys()}")

                # 序列化最终状态
                serialized_data = serialize_state_for_sse(last_state_data)
                print(f"[DEBUG] Final serialized data: {serialized_data}")

                interrupt_event = {
                    "type": "interrupt",
                    "thread_id": thread_id,
                    "data": serialized_data,
                }
                print(f"[DEBUG] Sending interrupt event: {interrupt_event}")
                yield f"data: {json.dumps(interrupt_event, ensure_ascii=False)}\n\n"
            else:
                # 正常完成，发送完成事件
                print(f"[DEBUG] Stream completed normally, sending done event")
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
    """恢复被中断的会话

    支持两种中断场景:
    1. param_required (参数补充): 用户补充缺失参数
       - confirm: 确认补充的参数
       - cancel: 取消操作

    2. authorization (授权): 工具执行前授权
       - approve: 批准执行（使用原参数）
       - edit: 编辑后执行（使用修改后的参数）
       - reject: 拒绝执行
    """
    print(f"[RESUME] Thread: {thread_id}, Config values: {config_values}")

    tools = get_default_tools()
    graph = get_agent_graph(tools)
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # 获取当前状态
        current_state = graph.get_state(config)
        pending_config = current_state.values.get("pending_config")
        interrupt_type = pending_config.get("interrupt_type") if pending_config else None

        print(f"[RESUME] Interrupt type: {interrupt_type}")
        print(f"[RESUME] Pending config: {pending_config}")

        # 解析 action - 支持 _action (旧) 和 action (新) 字段
        action_str = config_values.get("_action") or config_values.get("action")
        step_id = pending_config.get("step_id") if pending_config else None

        # 将 action 字符串转换为 HITLAction 枚举
        try:
            action = HITLAction(action_str) if action_str else None
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action_str}")

        if not action:
            raise HTTPException(status_code=400, detail="Missing action field")

        # 处理拒绝/取消操作
        if action in (HITLAction.REJECT, HITLAction.CANCEL):
            print(f"[RESUME] User {action.value} the operation")

            todo_list = list(current_state.values.get("todo_list", []))
            if step_id:
                for step in todo_list:
                    if step.get("id") == step_id:
                        step["status"] = "failed"
                        step["error"] = "用户取消" if action == HITLAction.CANCEL else "用户拒绝"
                        break

            reject_msg = AIMessage(content="已取消此操作。")

            # 使用 HITLMessageEncoder 创建取消消息（用于状态记录）
            hitl_msg = HITLMessageEncoder.encode(
                action=action,
                values={},
                pending_config=pending_config,
            )

            updates = {
                "pending_config": None,
                "final_status": "failed",
                "todo_list": todo_list,
                "messages": [hitl_msg, reject_msg],
                "error_info": "用户取消" if action == HITLAction.CANCEL else "用户拒绝",
            }

            graph.update_state(config, updates)
            updated_state = graph.get_state(config)
            return state_to_response(updated_state.values, thread_id)

        # 处理确认/批准/编辑操作
        clean_values = {k: v for k, v in config_values.items() if not k.startswith("_") and k != "action"}

        # 根据 action 类型映射到正确的 HITLAction
        # approve -> APPROVE, edit -> EDIT, confirm -> CONFIRM
        if action_str == "confirm":
            action = HITLAction.CONFIRM
        elif action_str == "approve":
            action = HITLAction.APPROVE
        elif action_str == "edit":
            action = HITLAction.EDIT

        # 使用 HITLMessageEncoder 创建消息
        user_input_msg = HITLMessageEncoder.encode(
            action=action,
            values=clean_values,
            pending_config=pending_config,
        )

        updates = {
            "pending_config": None,
            "final_status": "running",
            "messages": [user_input_msg],
        }

        print(f"[RESUME] Updating state with HITL message: action={action.value}")
        graph.update_state(config, updates)

        # 继续执行
        print(f"[RESUME] Invoking graph to continue execution...")
        result = graph.invoke(None, config=config)

        print(f"[RESUME] Execution completed, final status: {result.get('final_status')}")
        return state_to_response(result, thread_id)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[RESUME] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
