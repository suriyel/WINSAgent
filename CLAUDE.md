# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WINS Agent is an AI task orchestration platform built on **LangGraph 1.0** and **FastAPI**. It features multi-agent collaboration, human-in-the-loop capabilities, and real-time task visualization using SSE streaming.

**Tech Stack:**
- **Frontend:** React 18, Vite, TailwindCSS, Zustand (state), TanStack Query
- **Backend:** FastAPI, LangGraph 1.0.6, LangChain 1.2.6
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
npm run lint  # ESLint
npm run build  # Production build
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
- **`agents/hitl.py`** - HITL protocol: HITLAction enum, encoder/decoder, config builders
- **`agents/supervisor.py`** - Routing & coordination
- **`agents/planner.py`** - Task decomposition
- **`agents/executor.py`** - Tool execution with HITL interrupts
- **`agents/context_manager.py`** - Token budget, message compression, tool metadata trimming
- **`tools/base.py`** - ToolRegistry and @tool decorators
- **`knowledge/retriever.py`** - RAG with FAISS + DashScope
- **`api/chat.py`** - `/chat/stream` (SSE), `/chat/resume/{thread_id}`, `/chat/state/{thread_id}`
- **`config.py`** - Environment settings, token limits (4000 tokens)

### Key Frontend Modules (`frontend/src/`)
- **`stores/chatStore.ts`** - Zustand store (threadId, messages, todoList, pendingConfig)
- **`types/index.ts`** - TypeScript interfaces
- **`pages/Workstation.tsx`** - Main 3-column layout
- **`hooks/useChat.ts`** - SSE streaming, submit/approve/reject config handlers
- **`components/ConfigModal/`** - Dynamic form for HITL interrupts
- **`components/TodoList/`** - Task steps with progress visualization

### Human-in-the-Loop Protocol (`agents/hitl.py`)

Centralized HITL communication with type-safe encoding/decoding:

**Components:**
- `HITLAction` enum: `approve`, `edit`, `confirm`, `reject`, `cancel`
- `HITLMessageEncoder`: Encodes user actions to HumanMessage for graph state
- `HITLMessageDecoder`: Decodes HumanMessage to HITLResumeData for executor
- Config builders: `create_authorization_config()`, `create_param_required_config()`, `create_user_input_config()`

**Flow:**
1. Executor creates `pending_config` using config builders, sets `final_status="waiting_input"`
2. SSE sends "interrupt" event to frontend with `pending_config`
3. User interacts with ConfigModal (approve/edit/reject)
4. Frontend calls `POST /chat/resume/{thread_id}` with `action` field
5. Backend uses `HITLMessageEncoder.encode()` to create structured message
6. Executor uses `HITLMessageDecoder.decode()` to parse and resume execution

### Context Management (`agents/context_manager.py`)
The `ContextManager` class handles token budget enforcement:
- `compress_completed_steps()` - Replaces tool call/result pairs with summaries
- `trim_tool_metadata()` - Removes verbose internal metadata from ToolMessages
- `enforce_token_budget()` - Trims middle messages, preserving first and recent
- `optimize_context()` - Applies all three in sequence

## API Endpoints (v1)

- `POST /chat/stream` - Send message with SSE streaming
- `POST /chat/resume/{thread_id}` - Resume after interrupt
  - Body: `{action: "approve"|"edit"|"confirm"|"reject"|"cancel", ...values}`
  - Supports legacy `_action` field for backward compatibility
- `GET /chat/state/{thread_id}` - Get conversation state
- `GET /tools/` - List available tools
- `POST /knowledge/search` - Search knowledge base

## Environment Configuration

Required in `backend/.env` (copy from `.env.example`):
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

## Configuration Options (`config.py`)

Key settings:
- `message_token_limit: int = 4000` - Token budget for context
- `max_steps: int = 20` - Maximum execution steps
- `max_retries: int = 3` - Tool retry count
- `tool_timeout: int = 60` - Tool execution timeout (seconds)
- `recursion_limit: int = 25` - LangGraph recursion limit
- `tools_require_approval: list[str]` - Tools requiring HITL authorization
- `require_approval_for_all_tools: bool` - Global HITL flag

## Design System

Neo-Swiss style: Lavender Purple (#A78BFA), Sky Blue (#60A5FA), Mint Green (#34D399). Grid layout with generous whitespace.
