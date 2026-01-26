# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WINS Agent is an AI task orchestration platform built on **LangGraph 1.0** and **FastAPI**. It features ReAct-based agent orchestration, human-in-the-loop capabilities, and real-time task visualization using SSE streaming.

**Tech Stack:**
- **Frontend:** React 18, Vite, TailwindCSS, Zustand (state), TanStack Query
- **Backend:** FastAPI, LangGraph 1.0.6 (`create_react_agent`), LangChain 1.2.5
- **LLM:** Qwen3-72B-Instruct (via DashScope OpenAI-compatible API)
- **Vector Store:** FAISS with DashScope Embeddings
- **Persistence:** Redis (checkpointer, prod), InMemorySaver (dev), InMemoryStore (sessions)

## Commands

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
python run.py  # http://localhost:8000 (uses config from .env)
# Alternative: python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # http://localhost:3000, proxies /api to backend
npm run lint  # ESLint
npm run build  # TypeScript check + production build
npm run preview  # Preview production build
```

**Note:** Vite config uses `@/` as path alias for `./src/`

### Full Stack
```bash
./scripts/start-dev.sh  # Linux/macOS
scripts\start-dev.bat   # Windows
```

## Architecture

### Agent v2 Workflow (LangGraph ReAct)

The system now uses LangGraph's `create_react_agent` as the single entry point, replacing the previous hand-coded multi-node graph architecture:

```
User Input → [Main Agent (ReAct)]
                 │
                 ├─ LLM reasoning
                 ├─ Tool selection & execution
                 ├─ interrupt() for HITL
                 └─ Result synthesis
                     │
                     ▼
          ┌─────────────────────┐
          │   Available Tools    │
          ├─────────────────────┤
          │ • write_todos        │ ─ Todo management
          │ • read_todos         │
          │ • update_todo_step   │
          │ • request_human_*    │ ─ HITL (interrupt() based)
          │ • search_knowledge   │ ─ Business tools
          │ • create_task        │
          │ • calculate          │
          │ • read_file/write_* │
          │ • http_request       │
          │ • planner_expert     │ ─ SubAgent as tool
          │ • validator_expert   │   (agent.as_tool())
          │ • research_expert    │
          └─────────────────────┘
```

**Key architectural changes from v1:**
- **Removed:** supervisor.py, executor.py, replanner.py, goal_evaluator.py nodes
- **Added:** Single `main_agent.py` using `create_react_agent`
- **HITL:** Now uses native `interrupt()` instead of custom protocol
- **Context:** Managed via `pre_model_hook` middleware
- **SubAgents:** Implemented via `agent.as_tool()` pattern

### Key Backend Modules (`backend/app/`)

**Core Agent:**
- **`agents/main_agent.py`** - Main entry point using `create_react_agent()`. Contains:
  - `create_main_agent()` - Agent factory with tool assembly
  - `get_agent()` - Singleton instance
  - `get_checkpointer()` / `get_store()` - Persistence management
  - `invoke_agent()` / `stream_agent()` - Convenience wrappers
- **`agents/llm.py`** - LLM initialization (Qwen3 via DashScope OpenAI-compatible endpoint)

**Middleware:**
- **`agents/middleware/context.py`** - Context management via `pre_model_hook`:
  - `create_context_middleware()` - Token budget enforcement, tool result compression
  - `ContextConfig` - Configuration dataclass

**Tools:**
- **`agents/tools/todos.py`** - Todo management: `write_todos`, `read_todos`, `update_todo_step`
- **`agents/tools/hitl.py`** - HITL using native `interrupt()`: `request_human_approval`, `request_human_input`
- **`agents/tools/business.py`** - Business tools: search_knowledge, create_task, calculate, file ops, http_request, etc.
- **`tools/base.py`** - ToolRegistry (legacy, less used in v2)

**SubAgents (as Tools):**
- **`agents/subagents/planner.py`** - Planning expert SubAgent (via `agent.as_tool()`)
- **`agents/subagents/validator.py`** - Validation expert SubAgent
- **`agents/subagents/research.py`** - Research expert SubAgent

**Knowledge & API:**
- **`knowledge/retriever.py`** - RAG with FAISS + DashScope (model: text-embedding-v3)
- **`api/chat.py`** - `/chat/stream` (SSE with `astream_events`), `/chat/resume/{thread_id}` (Command(resume=)), `/chat/state/{thread_id}`
- **`api/conversations.py`** - Conversation CRUD
- **`api/tasks.py`** - Task persistence
- **`api/knowledge.py`** - Knowledge base management
- **`api/tools.py`** - Tool listing
- **`config.py`** - Simplified settings (message_token_limit, recursion_limit, tools_require_approval)

### Key Frontend Modules (`frontend/src/`)
- **`stores/chatStore.ts`** - Zustand store (threadId, messages, todoList, pendingConfig)
- **`types/index.ts`** - TypeScript interfaces
- **`pages/Workstation.tsx`** - Main 3-column layout with resizable sidebar (200px-500px, persisted to localStorage)
- **`hooks/useChat.ts`** - SSE streaming, submit/approve/reject config handlers
- **`components/ConfigModal/`** - Dynamic form for HITL interrupts
- **`components/TodoList/`** - Task steps with progress visualization
- **`components/HumanInput/InlineHumanInput.tsx`** - Inline HITL input (alternative to ConfigModal)
- **`utils/cn.ts`** - `clsx` + `tailwind-merge` utility for className merging

### Human-in-the-Loop Protocol (`agents/tools/hitl.py`)

HITL now uses LangGraph's native `interrupt()` mechanism:

**Tools:**
- `request_human_approval(action, tool_name, params)` - Request authorization for sensitive operations
- `request_human_input(question, context)` - Request user input for missing information

**Interrupt Types:**
- `authorization` - Tool execution authorization required
- `input_required` - User input needed

**Flow:**
1. Agent calls HITL tool (e.g., `request_human_approval`)
2. Tool invokes `interrupt(data)` - pauses graph execution
3. API detects interrupt via `state.tasks` and sends "interrupt" SSE event
4. User interacts with ConfigModal (approve/edit/reject/confirm)
5. Frontend calls `POST /chat/resume/{thread_id}` with `action` field
6. Backend resumes with `Command(resume=resume_data)`
7. Tool receives `human_response` and returns result
8. Agent continues execution

**Supported Actions:**
- `approve` - Execute with original parameters
- `reject` / `cancel` - Cancel execution
- `edit` - Modify parameters before execution
- `confirm` - Submit user input

### Context Management (`agents/middleware/context.py`)

Implemented via `pre_model_hook` in `create_react_agent`:

**`ContextConfig` dataclass:**
- `max_tokens: int = 4000` - Token budget
- `compress_tool_results: bool = True` - Truncate long tool outputs
- `tool_result_max_length: int = 500` - Max length for tool results
- `preserve_recent_messages: int = 10` - Keep last N messages

**Middleware functions:**
- `create_context_middleware(config, summarization_model)` - Returns `pre_model_hook` function
- `_compress_tool_messages()` - Truncates ToolMessage content
- `_trim_messages_smart()` - Intelligent message trimming (preserves system + first + recent)

**Hook behavior:**
Returns `{"llm_input_messages": [...]}` - modified messages for LLM input only (doesn't mutate state)

### Todo Management (`agents/tools/todos.py`)

Todo tools use LangGraph Store for persistence:

**Tools:**
- `write_todos(goal, steps, config)` - Create/update task plan
- `read_todos(config)` - Read current plan and progress
- `update_todo_step(step_index, status, result, config)` - Update step status

**TodoStep Status Values:** `pending`, `running`, `completed`, `failed`, `skipped`

**Storage:** Uses `get_store()` with namespace `("todos",)` and thread_id as key

### SubAgent Tools (`agents/subagents/`)

SubAgents are implemented via `agent.as_tool()` pattern:

**Available SubAgents:**
- `planner_expert` - Task planning and decomposition
- `validator_expert` - Result validation and quality assessment
- `research_expert` - Deep research with knowledge base access

**Implementation:** Each SubAgent is a separate `create_react_agent` instance converted to a tool via `.as_tool(name, description, arg_types)`

## API Endpoints (v1)

**Chat API:**
- `POST /api/v1/chat/stream` - Send message with SSE streaming
- `POST /api/v1/chat/resume/{thread_id}` - Resume after interrupt
  - Body: `{action: "approve"|"edit"|"confirm"|"reject"|"cancel", ...values}`
  - Supports legacy `_action` field for backward compatibility
- `GET /api/v1/chat/state/{thread_id}` - Get conversation state

**Conversations API:**
- `GET /api/v1/conversations/` - List conversations (query: `skip`, `limit`)
- `GET /api/v1/conversations/{thread_id}` - Get conversation details
- `POST /api/v1/conversations/create` - Create new conversation
- `PUT /api/v1/conversations/{thread_id}` - Update conversation (title, last_message)
- `DELETE /api/v1/conversations/{thread_id}` - Delete conversation (also clears Redis state)

**Tasks API:**
- `GET /api/v1/tasks/` - List tasks (query: `skip`, `limit`)
- `GET /api/v1/tasks/{task_id}` - Get task details
- `POST /api/v1/tasks/create` - Create new task
- `PUT /api/v1/tasks/{task_id}/status` - Update task status
- `DELETE /api/v1/tasks/{task_id}` - Delete task
- `GET /api/v1/tasks/{task_id}/steps` - Get task steps

**Knowledge API:**
- `POST /api/v1/knowledge/search` - Search knowledge base
- `POST /api/v1/knowledge/add` - Add document to knowledge base
- `POST /api/v1/knowledge/upload` - Upload .txt/.md files (UTF-8, chunked by paragraph)
- `DELETE /api/v1/knowledge/clear` - Clear entire knowledge base
- `GET /api/v1/knowledge/stats` - Get knowledge base statistics

**Tools API:**
- `GET /api/v1/tools/` - List all tools with approval status
- `GET /api/v1/tools/{name}` - Get tool details
- `GET /api/v1/tools/{name}/schema` - Get tool parameter schema

**Health:**
- `GET /health` - Health check (returns status and version)

**SSE Event Types (v2):**
- `update` - Streaming updates from `astream_events`:
  - `on_chat_model_stream` → content chunks
  - `on_tool_start` → tool invocation start
  - `on_tool_end` → tool completion
- `interrupt` - HITL interrupt (detected via `state.tasks`)
- `done` - Completion with final status and todo_list from Store
- `error` - Error events

## Environment Configuration

Required in `backend/.env` (copy from `.env.example`):

**LLM:**
- `DASHSCOPE_API_KEY` - For LLM and embeddings
- `LLM_MODEL` - Model name (default: qwen3-72b-instruct)

**Database:**
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` - Task persistence

**Redis:**
- `REDIS_URL` - For production checkpointing

**Vector Store:**
- `FAISS_INDEX_PATH` - Path to FAISS index (default: ./data/faiss_index)

**Server:**
- `API_HOST` - Server host (default: 0.0.0.0)
- `API_PORT` - Server port (default: 8000)
- `DEBUG` - Debug mode flag

Dev uses InMemorySaver (state lost on restart). Production requires Redis.

**API Docs:** http://localhost:8000/docs (Swagger UI)

**Note:** No test suite currently exists. When adding tests, create `backend/tests/` and `frontend/src/**/*.test.tsx`.

## Adding New Tools

Create `@tool` decorated functions in `backend/app/agents/tools/business.py`:

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    """Tool input schema"""
    param: str = Field(description="Parameter description")

@tool(args_schema=MyToolInput)
def my_tool(param: str) -> str:
    """Tool description for LLM. Be clear and concise."""
    return result

# Register in get_business_tools()
def get_business_tools() -> list[BaseTool]:
    return [
        search_knowledge,
        my_tool,  # Add here
        # ... other tools
    ]
```

**Key points:**
- Tool docstrings are shown to the LLM - make them clear and actionable
- Use Pydantic schemas for structured inputs
- For HITL-required tools, add tool name to `tools_require_approval` in config.py
- Tools with `config: RunnableConfig` parameter can access thread_id and Store

## Configuration Options (`config.py`)

Simplified v2 configuration:

**Agent Settings:**
- `message_token_limit: int = 4000` - Token budget for context
- `recursion_limit: int = 50` - LangGraph recursion limit

**Human-in-the-Loop:**
- `tools_require_approval: list[str] = ["write_file", "http_request", "send_email"]` - Tools requiring HITL
- `require_approval_for_all_tools: bool = False` - Global HITL flag

**Note:** v2 architecture removed `max_steps`, `max_retries`, `tool_timeout`, and replanning settings. The ReAct agent handles retries and replanning autonomously based on its reasoning.

## Architecture Documentation

Detailed v2 design rationale in `docs/architecture-v2.md`:
- Design philosophy: "Agent First" approach using LangGraph native capabilities
- Comparison with v1 architecture
- Code examples for all components
- API layer design with SSE streaming

## Design System

Neo-Swiss style: Lavender Purple (#A78BFA), Sky Blue (#60A5FA), Mint Green (#34D399). Grid layout with generous whitespace.

## Backward Compatibility Notes

The `agents/__init__.py` provides deprecated aliases:
- `get_agent_graph()` → use `get_agent()` instead
- `build_agent_graph()` → use `create_main_agent()` instead

Legacy files (supervisor.py, planner.py, executor.py, validator.py, hitl.py, graph.py, state.py) may still exist but are unused in v2 architecture.
