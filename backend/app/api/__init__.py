"""
API 路由模块
"""

from fastapi import APIRouter
from .chat import router as chat_router
from .tasks import router as tasks_router
from .conversations import router as conversations_router

api_router = APIRouter()

api_router.include_router(chat_router, prefix="/chat", tags=["Chat"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(conversations_router, prefix="/conversations", tags=["Conversations"])
