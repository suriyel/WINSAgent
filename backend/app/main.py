"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    # Startup: build knowledge vector stores if documents exist
    from app.knowledge.vector_store import knowledge_manager

    knowledge_manager.initialize()
    yield
    # Shutdown: nothing to clean up for InMemory stage


app = FastAPI(
    title="WINS Agent Workstation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register routers ---
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.hitl import router as hitl_router
from app.api.knowledge_api import router as knowledge_router
from app.api.tasks import router as tasks_router
from app.api.tools_api import router as tools_router

app.include_router(chat_router, prefix="/api")
app.include_router(hitl_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(tools_router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    # 这里的 app.main:app 对应你命令行里的路径
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)