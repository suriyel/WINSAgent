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
venv\Scripts\activate  # Windows: source venv/bin/activate on Linux/macOS
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

### Multi-Agent Workflow
```
User Input → [Supervisor] → routes to:
  ├→ [Planner] - Intent parsing, task decomposition
  ├→ [Executor] - Tool invocation (interrupt_before for HITL)
  │     ├→ (success) → Goal Evaluator → skip remaining if goal achieved
  │     └→ (failure after max retries) → Create ReplanContext
  ├→ [Replanner] - Generate revised plan on failure (NEW)
  └→ [Validator] - Result validation, error attribution
```

### Key Backend Modules (`backend/app/`)
- **`agents/state.py`** - AgentState TypedDict (messages, todo_list, pending_config, replan_context, goal_achieved)
- **`agents/graph.py`** - StateGraph assembly with interrupt handling
- **`agents/hitl.py`** - HITL protocol: HITLAction enum, encoder/decoder, config builders
- **`agents/supervisor.py`** - Routing & coordination (planner/executor/replanner/validator)
- **`agents/planner.py`** - Task decomposition
- **`agents/executor.py`** - Tool execution with HITL interrupts, replan triggers, goal evaluation
- **`agents/replanner.py`** - Dynamic replanning on failure (NEW)
- **`agents/goal_evaluator.py`** - Early goal completion detection (NEW)
- **`agents/context_manager.py`** - Token budget, message compression, tool metadata trimming
- **`tools/base.py`** - ToolRegistry and @tool decorators
- **`knowledge/retriever.py`** - RAG with FAISS + DashScope (model: text-embedding-v3)
- **`api/chat.py`** - `/chat/stream` (SSE), `/chat/resume/{thread_id}`, `/chat/state/{thread_id}`
- **`api/conversations.py`** - Conversation CRUD with Redis state cleanup
- **`api/tasks.py`** - Task persistence
- **`api/knowledge.py`** - Knowledge base management
- **`api/tools.py`** - Tool listing
- **`config.py`** - Environment settings, token limits (4000 tokens), replan config

### Key Frontend Modules (`frontend/src/`)
- **`stores/chatStore.ts`** - Zustand store (threadId, messages, todoList, pendingConfig)
- **`types/index.ts`** - TypeScript interfaces
- **`pages/Workstation.tsx`** - Main 3-column layout with resizable sidebar (200px-500px, persisted to localStorage)
- **`hooks/useChat.ts`** - SSE streaming, submit/approve/reject config handlers
- **`components/ConfigModal/`** - Dynamic form for HITL interrupts
- **`components/TodoList/`** - Task steps with progress visualization
- **`components/HumanInput/InlineHumanInput.tsx`** - Inline HITL input (alternative to ConfigModal)
- **`utils/cn.ts`** - `clsx` + `tailwind-merge` utility for className merging

### Human-in-the-Loop Protocol (`agents/hitl.py`)

Centralized HITL communication with type-safe encoding/decoding:

**Components:**
- `HITLAction` enum: `approve`, `edit`, `confirm`, `reject`, `cancel`
- `HITLMessageEncoder`: Encodes user actions to HumanMessage for graph state
- `HITLMessageDecoder`: Decodes HumanMessage to HITLResumeData for executor
- Config builders: `create_authorization_config()`, `create_param_required_config()`, `create_user_input_config()`

**Interrupt Types:**
- `authorization` - Tool execution authorization required
- `param_required` - Missing required parameters

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

### State Helpers (`agents/state.py`)
Utility functions for state management:
- `create_initial_state()` - Creates default AgentState
- `create_todo_step()` - Creates a TodoStep
- `create_replan_context()` - Creates ReplanContext
- `skip_remaining_steps()` - Marks remaining steps as skipped

### Tool Registry (`tools/base.py`)
The `ToolRegistry` class manages tool registration:
- `register()` - Register a tool (auto-called by @tool decorator)
- `get(name)` - Get a specific tool
- `get_all()` - Get all registered tools
- `clear()` - Clear all registered tools

### Dynamic Replanning (`agents/replanner.py`, `agents/goal_evaluator.py`)

Intelligent task recovery and early completion detection:

**Components:**
- `ReplanContext`: Captures failure context (trigger_reason, failed_step, completed_results)
- `replanner_node`: LLM-powered plan revision with 4 strategies
- `goal_evaluator`: Detects early goal completion to skip unnecessary steps

**Replan Strategies:**
| Strategy | When Used | Action |
|----------|-----------|--------|
| `replace_failed` | Tool-specific error | Replace step with alternative tool |
| `alternative_approach` | Approach fundamentally broken | Redesign remaining steps |
| `skip_failed` | Step not critical | Mark as skipped, continue |
| `abort` | Unrecoverable | Go to validator with failure |

**Flow:**
1. Step fails after max retries → Executor creates `ReplanContext`
2. Supervisor routes to Replanner node
3. Replanner generates revised plan using LLM
4. Merged plan resumes execution from Supervisor

**Goal Evaluation (on-demand):**
1. Step completes successfully with success indicators ("完成", "成功", etc.)
2. `should_evaluate_goal()` heuristic triggers evaluation
3. LLM evaluates if original intent is satisfied
4. If goal achieved → remaining steps marked as "skipped" → Validator

**TodoStep Status Values:**
- `pending` - Not yet started
- `running` - Currently executing
- `completed` - Successfully finished
- `failed` - Failed after retries
- `skipped` - Skipped (goal achieved early or replanning)

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

**SSE Event Types:**
- `update` - Streaming updates (node, content, todo_list, status, pending_config)
- `interrupt` - HITL interrupt with pending_config
- `done` - Completion with final status and todo_list
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

**Dynamic Replanning Settings:**
- `replan_enabled: bool = True` - Enable/disable replanning feature
- `max_replans: int = 3` - Maximum replan attempts per task
- `goal_evaluation_enabled: bool = True` - Enable/disable early goal detection
- `replan_on_max_retries: bool = True` - Trigger replan when step hits max retries

## Design System

Neo-Swiss style: Lavender Purple (#A78BFA), Sky Blue (#60A5FA), Mint Green (#34D399). Grid layout with generous whitespace.
