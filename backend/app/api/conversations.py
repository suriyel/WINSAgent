"""
对话历史 API 路由
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime

from app.models.schemas import ConversationInfo, ConversationListResponse

router = APIRouter()

# 内存存储（生产环境应使用数据库）
_conversations_store: dict[str, ConversationInfo] = {}


@router.get("/", response_model=ConversationListResponse)
async def list_conversations(skip: int = 0, limit: int = 20):
    """获取对话列表"""
    conversations = list(_conversations_store.values())
    conversations.sort(key=lambda x: x.updated_at, reverse=True)

    return ConversationListResponse(
        conversations=conversations[skip : skip + limit],
        total=len(conversations),
    )


@router.get("/{thread_id}", response_model=ConversationInfo)
async def get_conversation(thread_id: str):
    """获取对话详情"""
    if thread_id not in _conversations_store:
        raise HTTPException(status_code=404, detail="对话不存在")

    return _conversations_store[thread_id]


@router.post("/create", response_model=ConversationInfo)
async def create_conversation(thread_id: str, title: str | None = None):
    """创建新对话"""
    conversation = ConversationInfo(
        thread_id=thread_id,
        title=title or "新对话",
        last_message=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    _conversations_store[thread_id] = conversation
    return conversation


@router.put("/{thread_id}")
async def update_conversation(
    thread_id: str,
    title: str | None = None,
    last_message: str | None = None,
):
    """更新对话信息"""
    if thread_id not in _conversations_store:
        # 自动创建
        _conversations_store[thread_id] = ConversationInfo(
            thread_id=thread_id,
            title=title or "新对话",
            last_message=last_message,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    else:
        conv = _conversations_store[thread_id]
        if title:
            conv.title = title
        if last_message:
            conv.last_message = last_message
        conv.updated_at = datetime.now()

    return _conversations_store[thread_id]


@router.delete("/{thread_id}")
async def delete_conversation(thread_id: str):
    """删除对话"""
    if thread_id not in _conversations_store:
        raise HTTPException(status_code=404, detail="对话不存在")

    # 从存储中删除对话记录
    del _conversations_store[thread_id]

    # 同时删除 LangGraph 的 thread state
    try:
        from app.agents.graph import get_agent_graph
        from app.config import get_settings

        graph = get_agent_graph()
        settings = get_settings()

        # 如果使用 Redis 作为 checkpointer，清理 Redis 中的数据
        if settings.redis_url:
            import redis

            redis_client = redis.from_url(settings.redis_url, decode_responses=True)
            # LangGraph Redis checkpointer 存储格式: checkpointer:{thread_id}*
            pattern = f"checkpointer:{thread_id}*"
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)
                print(f"[DEBUG] Deleted {len(keys)} Redis keys for thread {thread_id}")
    except Exception as e:
        print(f"[DEBUG] Failed to delete graph state for thread {thread_id}: {e}")

    return {"message": "对话删除成功", "thread_id": thread_id}
