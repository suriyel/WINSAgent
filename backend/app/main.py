"""
FastAPI 应用主入口 (v2)

基于 LangGraph create_react_agent 的新架构
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()

    # 启动时
    print("=" * 50)
    print("🚀 WINS Agent v2 启动中...")
    print(f"📍 API 地址: http://{settings.api_host}:{settings.api_port}")
    print(f"🔧 调试模式: {settings.debug}")

    # 初始化 Agent
    from app.agents import get_agent
    from app.agents.tools import get_business_tools, get_todo_tools, get_hitl_tools

    agent = get_agent()
    print("🤖 Main Agent 初始化完成")

    # 统计工具数量
    business_tools = get_business_tools()
    todo_tools = get_todo_tools()
    hitl_tools = get_hitl_tools()
    total_tools = len(business_tools) + len(todo_tools) + len(hitl_tools) + 3  # +3 for subagent tools

    print(f"🔧 已加载工具:")
    print(f"   - 业务工具: {len(business_tools)} 个")
    print(f"   - TODO 工具: {len(todo_tools)} 个")
    print(f"   - HITL 工具: {len(hitl_tools)} 个")
    print(f"   - SubAgent 工具: 3 个")
    print(f"   - 总计: {total_tools} 个")

    print("=" * 50)
    print("✅ WINS Agent v2 就绪!")
    print(f"📖 API 文档: http://{settings.api_host}:{settings.api_port}/docs")
    print("=" * 50)

    yield

    # 关闭时
    print("👋 WINS Agent v2 正在关闭...")
    from app.agents import reset_agent
    reset_agent()
    print("✅ 资源已清理")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    settings = get_settings()

    app = FastAPI(
        title="WINS Agent API",
        description="""
基于 LangGraph create_react_agent 的智能任务编排平台 API (v2)

## 核心特性

- **Agent First**: 基于 LangGraph 原生 ReAct Agent
- **Tool-based Planning**: 通过 write_todos 工具实现任务规划
- **Native HITL**: 使用 interrupt() 实现人机交互
- **SubAgent as Tool**: 专家 Agent 作为工具被调用
- **Context Middleware**: 自动上下文裁剪和管理

## API 端点

- `POST /api/v1/chat/stream` - 流式对话
- `POST /api/v1/chat/resume/{thread_id}` - 恢复中断
- `GET /api/v1/chat/state/{thread_id}` - 获取会话状态
        """,
        version="2.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS 配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应限制
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(api_router, prefix="/api/v1")

    # 健康检查
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "version": "2.0.0",
            "architecture": "langgraph-react-agent",
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
