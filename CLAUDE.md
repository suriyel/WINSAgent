# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WINS Agent is an AI task orchestration platform built on **LangGraph 1.0** and **FastAPI**. It features multi-agent collaboration, human-in-the-loop capabilities, and real-time task visualization using SSE streaming.

**Tech Stack:**
- **Frontend:** React 18, Vite, TailwindCSS, Zustand (state), TanStack Query
- **Backend:** FastAPI, LangGraph 1.0.6, LangChain 1.2.5
- **LLM:** Qwen3-72B-Instruct (via DashScope API)
- **Vector Store:** FAISS with DashScope Embeddings
- **Persistence:** Redis (checkpointer), MySQL, InMemorySaver (dev)

## Commands

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --reload  # http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # http://localhost:3000, proxies /api to backend
```

### Full Stack
```bash
./scripts/start-dev.sh  # Linux/macOS
scripts\start-dev.bat   # Windows
```

## Architecture

### Multi-Agent Workflow
```
User Input → [Supervisor] → routes to:
  ├→ [Planner] - Intent parsing, task decomposition
  ├→ [Executor] - Tool invocation (interrupt_before for HITL)
  └→ [Validator] - Result validation, error attribution
```

### Key Backend Modules (`backend/app/`)
- **`agents/state.py`** - AgentState TypedDict (messages, todo_list, pending_config)
- **`agents/graph.py`** - StateGraph assembly with interrupt handling
- **`agents/supervisor.py`** - Routing & coordination
- **`agents/planner.py`** - Task decomposition
- **`agents/executor.py`** - Tool execution with HITL interrupts
- **`tools/base.py`** - ToolRegistry and @tool decorators
- **`knowledge/retriever.py`** - RAG with FAISS + DashScope
- **`api/chat.py`** - `/chat/send`, `/chat/stream` (SSE), `/chat/resume`
- **`config.py`** - Environment settings, token limits (4000 tokens)

### Key Frontend Modules (`frontend/src/`)
- **`stores/chatStore.ts`** - Zustand store (threadId, messages, todoList, pendingConfig)
- **`types/index.ts`** - TypeScript interfaces
- **`pages/Workstation.tsx`** - Main 3-column layout
- **`components/ConfigModal/`** - Dynamic form for HITL interrupts
- **`components/TodoList/`** - Task steps with progress visualization

### Human-in-the-Loop Flow
1. Executor sets `pending_config` with form fields, triggers interrupt
2. SSE sends "interrupt" event to frontend
3. User fills ConfigModal
4. `POST /chat/resume` resumes execution with form data

## API Endpoints (v1)

- `POST /chat/stream` - Send message with SSE streaming
- `POST /chat/resume` - Resume after interrupt
- `GET /chat/state/{thread_id}` - Get conversation state
- `GET /tools/` - List available tools
- `POST /knowledge/search` - Search knowledge base

## Environment Configuration

Required in `backend/.env`:
- `DASHSCOPE_API_KEY` - For LLM and embeddings
- `MYSQL_*` credentials - For task persistence
- `REDIS_URL` - For production checkpointing

Dev uses InMemorySaver (state lost on restart). Production requires Redis.

## Adding New Tools

Create `@tool` decorated functions in `backend/app/tools/base.py`:
```python
@tool(args_schema=MySchema)
def my_tool(param: str) -> str:
    """Tool description for LLM."""
    return result
```

Tool schemas auto-generate frontend ConfigFormField for parameter forms.

## Token Budget

4000 tokens allocated: system prompt (~500), knowledge (~1500), history (~1500), response (~500). Tool timeout: 60s with max 3 retries.

## Design System

Neo-Swiss style: Lavender Purple (#A78BFA), Sky Blue (#60A5FA), Mint Green (#34D399). Grid layout with generous whitespace.
