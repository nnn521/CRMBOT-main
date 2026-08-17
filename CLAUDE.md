# CRMBOT Project Rules

## Project Overview
CRMBOT is a Smart Sales AI Agent built with:
- **Backend**: FastAPI + LangGraph + PostgreSQL + FAISS
- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS + Zustand + TanStack Query + shadcn/ui  
- **Agent**: LangGraph StateGraph with PostgreSQL checkpointing
- **Model**: DeepSeek V4 Flash (via LiteLLM proxy)

## Architecture
```
用户 → frontend/React → backend/FastAPI → LangGraph Agent → DeepSeek LLM
                                          → PostgreSQL (state persistence)
                                          → FAISS (knowledge retrieval)
                                          → Document Generator
```

## Conventions
- Backend code uses `from app.xxx import yyy` pattern
- Frontend uses `@/` path alias for `src/`
- React components use named exports + default export
- State management: Zustand stores in `src/stores/`
- API calls: TanStack React Query in `src/api/`
- UI components: shadcn/ui in `src/components/ui/`

## Key Directories
- `backend/app/agents/` - LangGraph agent logic
- `backend/app/api/v1/` - REST API endpoints  
- `frontend/src/` - React application
- `data/knowledge_base/` - Product knowledge files
- `data/vector_store/` - FAISS vector indices

## Available Skills
- `skill-based-architecture` - Meta-skill for code analysis
- `project-architect` - Project architecture planning
- `frontend-toolkit` - Frontend design patterns
- `oop-architect` - OOP design with Mermaid UML
