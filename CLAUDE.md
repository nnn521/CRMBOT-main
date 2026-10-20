# CRMBOT Project Rules

## Project Overview
CRMBOT is a Smart Sales AI Agent built with:
- **Backend**: FastAPI + LangGraph + PostgreSQL + FAISS
- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS + Zustand + shadcn/ui
- **Agent**: LangGraph StateGraph with PostgreSQL checkpointing
- **Model**: DeepSeek (OpenAI-compatible API)

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
- State management: Zustand stores in `src/stores/`（仅客户端 UI 状态）
- API calls: typed fetch clients in `src/api/`，统一经 `src/lib/api.ts` 的 `apiFetch`
- 认证：JWT 经 httpOnly Cookie 下发（后端签发/吊销）；前端不落 token 到 localStorage
- UI components: shadcn/ui in `src/components/ui/`

## LangGraph State 约定（重要）
- 对话记忆由 checkpoint 维护（thread_id=session_id）；**客户端不得回传 history**
- 节点不得整体回传 `messages` 通道：非终态节点用 `strip_messages(state)`，
  终态节点用 `state_update_with_reply(state, reply)`（否则 add_messages 会重复追加）
- 最终状态通过 `graph.ainvoke()` 获取完整合并结果
- 清除会话历史必须同步调用 `clear_session_checkpoint(session_id)` 删除 Agent 记忆

## 安全基线
- `SECRET_KEY` 必须 ≥32 字符且非占位值（服务启动时强制校验）
- 所有用户输入进 LLM prompt 前经 `app.core.prompts` 的 `guard_user_content` /
  `guard_system_prompt` 处理
- 文档/图片文件名一律经 `_sanitize_filename_component` / `_resolve_model_dir` 消毒
- 路径类配置默认锚定 `backend/` 目录（不依赖进程 CWD）

## Key Directories
- `backend/app/agents/` - LangGraph agent logic
- `backend/app/api/v1/` - REST API endpoints
- `frontend/src/` - React application
- `backend/data/knowledge_base/` - Product knowledge files
- `backend/data/vector_store/` - FAISS vector indices
- `backend/tests/` - pytest regression suite

## Testing
- Backend: `python -m pytest` (从 `backend/` 目录运行；沙盒环境需 `PYTHONPATH=pylib`)
- Frontend: `npm run typecheck`（tsc 严格模式，含 noUnusedLocals/noUnusedParameters）
- 依赖锁定：`backend/requirements.txt` 全部精确锁版本

## Available Skills
- `skill-based-architecture` - Meta-skill for code analysis
- `project-architect` - Project architecture planning
- `frontend-toolkit` - Frontend design patterns
- `oop-architect` - OOP design with Mermaid UML
