# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WINS Agent Workstation is a full-stack AI Agent application for telecom network optimization simulation. It enables intelligent analysis of network coverage, interference, and capacity issues through digital twin scenarios, with root cause analysis and optimization simulation comparison.

**Tech Stack:**
- Backend: FastAPI + LangChain 1.2.5 + FAISS (Python)
- Frontend: React 18 + TypeScript + Vite + Tailwind CSS + Zustand

**Note:** The agent system prompt and UI copy are in Chinese.

## Build & Run Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Then configure LLM_API_KEY, LLM_BASE_URL
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Dev server on port 3000, proxies /api to backend
npm run build    # Production build (tsc -b && vite build)
npm run preview  # Preview production build
```

### Tests
```bash
cd backend
pytest tests/                          # All unit tests (mocked LLM, no API calls)
pytest tests/test_runner.py            # Single test file
pytest tests/test_runner.py::TestSubAgentRunner::test_compile_creates_agent  # Single test
pytest tests/ -m live                  # Live tests only (requires .env with real LLM_API_KEY)
pytest tests/ -m "not live"            # Unit tests only (explicit)
```

Tests use two modes controlled by the `@pytest.mark.live` marker:
- **Unit tests** (default): Auto-mocked settings via `conftest.py` `patch_settings` fixture; no API calls needed
- **Live tests**: Use real `.env` config to call LLM APIs; skip in CI or when no API key available

No frontend tests or linters are configured.

### Development Workflow
1. Backend runs on http://localhost:8000
2. Frontend Vite dev server on http://localhost:3000
3. Vite proxy redirects `/api/*` to backend
4. CORS allows both `localhost:3000` and `localhost:5173`

## Architecture

### Data Flow
```
User Input → FastAPI /api/chat (SSE) → LangChain Agent → Middleware Stack → Tool Execution → SSE Events → Frontend State (Zustand)
```

### Middleware Stack (execution order in `backend/app/agent/core.py`)
1. **SubAgentMiddleware** — Manages reactive sub-agents (e.g., TODO tracker) and delegated sub-agents; replaces the original TodoListMiddleware
2. **SuggestionsMiddleware** — Parses `suggestions` fenced blocks from LLM output into quick-reply chips
3. **ContextEditingMiddleware** — Clears old tool call/result messages when context exceeds 2000 tokens (keeps last 1)
4. **MissingParamsMiddleware** — Detects missing required tool parameters, triggers interrupt with a JSON Schema form for the user to fill (conditional: only added when tools have `param_edit_schema`)
5. **CustomHumanInTheLoopMiddleware** — Interrupts execution for tools marked `requires_hitl` (conditional: only added when tools have HITL config)

### SubAgent Framework (`backend/app/agent/subagents/`)
Two patterns for orchestrating sub-agents alongside the main agent:

- **Reactive sub-agents**: Triggered by hooks (e.g., `after_model`), run in the background to update state. The TODO tracker (`agents/todo_tracker.py`) is the primary example — it parses LLM output and updates `todos` state with step progress.
- **Delegated sub-agents**: Invoked explicitly via a `task()` tool injected by the middleware. They run in isolated context and return a string result.

Key components:
- `types.py` — `SubAgentConfig` TypedDict defining config schema
- `runner.py` — `SubAgentRunner` compiles configs into executable agents, caches LLM instances
- `middleware.py` — `SubAgentMiddleware` hooks into agent lifecycle, routes reactive triggers and task calls

### Tool System
Tools are registered in `backend/app/agent/tools/registry.py` with metadata:
- `requires_hitl`: Boolean — if true, tool execution pauses for user approval
- `category`: `"query"` (no HITL) or `"mutation"` (typically requires HITL)
- `param_edit_schema`: Optional JSON Schema for MissingParamsMiddleware forms

Query tools: `match_scenario`, `query_root_cause_analysis`, `query_simulation_results`, `search_terminology`, `search_design_doc`

### Knowledge System
Dual FAISS vector stores managed by `backend/app/knowledge/vector_store.py`:
- `terminology/` — Telecom network optimization terminology
- `design_docs/` — Cell-level and grid-level analysis workflow documents

Source markdown files live in `knowledge/`. Indexes persist to `backend/faiss_indexes/` and are rebuilt via `POST /api/knowledge/rebuild`. Uses `FakeEmbeddings` fallback when no LLM API key is configured.

### SSE Event Types
Events streamed from backend (`backend/app/sse/event_mapper.py`) to frontend:
- `thinking` — Token-level LLM output
- `tool.call` / `tool.result` — Tool execution lifecycle
- `todo.state` — Step progress updates
- `hitl.pending` — Human-in-the-loop approval required
- `params.pending` — Missing parameters need user input
- `suggestions` — Quick-reply chip options
- `message` — Final assistant response
- `error` — Error events

### Frontend State
Zustand store in `frontend/src/stores/chatStore.ts` manages:
- Conversations and message history
- Streaming state and thinking buffer
- HITL pending decisions (`pendingHITL`)
- Missing params pending decisions (`pendingParams`)
- TODO steps per task

Frontend uses `@/*` path alias mapped to `src/*` (configured in `vite.config.ts` and `tsconfig.json`).

### Frontend Layout
Three-column layout in `App.tsx`:
- **Sidebar:** `ConversationSidebar` — conversation list
- **Main:** `ChatArea` — messages, input bar, suggestion chips, HITL/params cards
- **Panel:** `TaskPanel` — task cards with TODO steppers

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app entry, lifespan init, router registration |
| `backend/app/config.py` | Configuration from `.env` via pydantic-settings |
| `backend/app/agent/core.py` | Agent builder with system prompt, middleware pipeline, singleton |
| `backend/app/agent/tools/registry.py` | Central tool registry with metadata |
| `backend/app/agent/tools/telecom_tools.py` | Telecom domain tools (scenario, RCA, simulation) |
| `backend/app/agent/tools/knowledge.py` | Knowledge retrieval tools (terminology, design docs) |
| `backend/app/agent/tools/hil.py` | Custom HITL middleware |
| `backend/app/agent/middleware/missing_params.py` | Missing params middleware + JSON Schema helpers |
| `backend/app/agent/middleware/suggestions.py` | Suggestions parsing middleware |
| `backend/app/agent/subagents/middleware.py` | SubAgent middleware — reactive hooks and task routing |
| `backend/app/agent/subagents/runner.py` | SubAgent runner — compiles configs, caches LLM instances |
| `backend/app/agent/subagents/agents/todo_tracker.py` | TODO tracker reactive sub-agent config |
| `backend/app/api/chat.py` | Chat SSE endpoint |
| `backend/app/sse/event_mapper.py` | Converts LangChain events to SSE frames |
| `backend/app/knowledge/vector_store.py` | FAISS manager (dual-store) |
| `backend/app/models/schemas.py` | Pydantic models for API request/response |
| `backend/tests/conftest.py` | Pytest fixtures: mock/real settings, sample messages, markers |
| `frontend/src/stores/chatStore.ts` | Zustand store (central state) |
| `frontend/src/services/sse.ts` | SSE connection manager (fetch-based streaming) |
| `frontend/src/design-tokens.ts` | Design system color/spacing tokens |

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat` | POST | Start/continue conversation (SSE stream) |
| `/api/hitl/{id}/decide` | POST | Submit HITL decision (approve/edit/reject) |
| `/api/params/{id}/decide` | POST | Submit missing parameter values |
| `/api/conversations` | GET | List all conversations |
| `/api/tasks/{id}/todos` | GET | Get TODO steps for task |
| `/api/tools` | GET | List registered tools with metadata |
| `/api/knowledge/rebuild` | POST | Rebuild FAISS indexes |
| `/health` | GET | Health check |

## Configuration

Backend config in `backend/app/config.py` loaded from `.env`:
- `LLM_MODEL` — Model identifier (default: `"openai:gpt-4o"`)
- `LLM_API_KEY` — Required for LLM
- `LLM_BASE_URL` — Optional, for OpenAI-compatible APIs (Qwen, LM Studio, etc.)
- `SUBAGENT_MODEL` — Optional, separate model for sub-agents (defaults to `LLM_MODEL`)
- `KNOWLEDGE_DIR` — Path to knowledge markdown files (default: `../knowledge`)
- `FAISS_INDEX_DIR` — Path to persist FAISS indexes (default: `./faiss_indexes`)
- `MYSQL_URL` — MySQL connection string (configured but not yet integrated)
- `CORS_ORIGINS` — Allowed CORS origins (default: `http://localhost:3000,http://localhost:5173`)

## Design System

Neo-Swiss International style with custom Tailwind colors defined in `frontend/tailwind.config.js`:
- Primary: `#A78BFA` (Lavender) — Interactive highlights
- Secondary: `#60A5FA` (Sky Blue) — Running state
- Success: `#34D399` (Mint) — Completed state
- Error: `#F87171` (Coral) — Failed state

Design tokens defined in `frontend/src/design-tokens.ts`. Typography uses Inter font family.

## Current Limitations (Validation Stage)

- Uses `InMemorySaver` checkpointer (state lost on restart)
- `FakeEmbeddings` fallback when no LLM API key
- MySQL config present but not integrated yet
- In-memory conversation storage (no persistence)
- No frontend tests, linting, or CI/CD pipeline configured
