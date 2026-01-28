# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WINS Agent Workstation is a full-stack AI Agent application that integrates with legacy business systems. It enables intelligent task orchestration through natural language with built-in human-in-the-loop (HITL) approval, TODO tracking, and domain knowledge retrieval.

**Tech Stack:**
- Backend: FastAPI + LangChain 1.2.5 + FAISS (Python)
- Frontend: React 18 + TypeScript + Vite + Tailwind CSS + Zustand

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
npm run build    # Production build (TypeScript check + Vite)
npm run preview  # Preview production build
```

### Development Workflow
1. Backend runs on http://localhost:8000
2. Frontend Vite dev server on http://localhost:3000
3. Vite proxy redirects `/api/*` to backend

## Architecture

### Data Flow
```
User Input → FastAPI /chat (SSE) → LangChain Agent → Middleware Stack → Tool Execution → SSE Events → Frontend State (Zustand)
```

### Middleware Stack
- **TodoListMiddleware**: Tracks task steps (pending/in_progress/completed)
- **CustomHumanInTheLoopMiddleware**: Interrupts execution for HITL-required tools

### Tool System
Tools are registered in `app/agent/tools/registry.py` with metadata:
- `requires_hitl`: Boolean - if true, tool execution pauses for user approval
- `category`: "query" (no HITL) or "mutation" (typically requires HITL)

Query tools: `search_customer`, `validate_customer`, `check_inventory`, `search_terminology`, `search_design_doc`
Mutation tools: `create_order` (requires HITL)

### Knowledge System
Dual FAISS vector stores in `app/knowledge/vector_store.py`:
- `terminology/` - Professional terminology
- `design_docs/` - System design documentation

Indexes are persisted to `backend/faiss_indexes/` and rebuilt via `/api/knowledge/rebuild`.

### SSE Event Types
Events streamed from backend to frontend:
- `thinking` - Token-level LLM output
- `tool.call` / `tool.result` - Tool execution
- `todo.state` - Step progress updates
- `hitl.pending` - Approval required
- `message` - Final response
- `error` - Error events

### Frontend State
Zustand store in `stores/chatStore.ts` manages:
- Conversations and message history
- Streaming state
- HITL pending decisions
- TODO steps per task

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/agent/core.py` | Agent builder with system prompt, middleware, and singleton |
| `backend/app/agent/tools/registry.py` | Central tool registry with metadata |
| `backend/app/agent/tools/hil.py` | Custom HITL middleware implementation |
| `backend/app/sse/event_mapper.py` | Converts LangChain output to SSE frames |
| `backend/app/knowledge/vector_store.py` | FAISS manager (dual-store) |
| `frontend/src/stores/chatStore.ts` | Zustand store (central state) |
| `frontend/src/services/sse.ts` | SSE connection manager |

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat` | POST | Start/continue conversation (SSE stream) |
| `/api/hitl/{id}/decide` | POST | Submit HITL decision (approve/edit/reject) |
| `/api/conversations` | GET | List all conversations |
| `/api/tasks/{id}/todos` | GET | Get TODO steps for task |
| `/api/tools` | GET | List registered tools with metadata |
| `/api/knowledge/rebuild` | POST | Rebuild FAISS indexes |

## Configuration

Backend config in `backend/app/config.py` loaded from `.env`:
- `LLM_MODEL` - Model identifier (default: "openai:gpt-4o")
- `LLM_API_KEY` - Required for LLM
- `LLM_BASE_URL` - Optional, for OpenAI-compatible APIs (Qwen, LM Studio, etc.)
- `KNOWLEDGE_DIR` - Path to knowledge markdown files
- `FAISS_INDEX_DIR` - Path to persist FAISS indexes

## Design System

Neo-Swiss International style with custom Tailwind colors:
- Primary: #A78BFA (Lavender) - Interactive highlights
- Secondary: #60A5FA (Sky Blue) - Running state
- Success: #34D399 (Mint) - Completed state
- Error: #F87171 (Coral) - Failed state

Design tokens defined in `frontend/src/design-tokens.ts`.

## Current Limitations (Validation Stage)

- Uses `InMemorySaver` checkpointer (state lost on restart)
- No test suite configured
- `FakeEmbeddings` fallback when no LLM API key
- MySQL config present but not integrated yet
