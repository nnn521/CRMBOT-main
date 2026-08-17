# Hermes 内部助手 —— Docker 整合方案

> 日期：2026-06-21 | 阶段五 | 状态：规划中

## 1. 目标

在 CRMBOT B端 「Hermes 内部助手」卡片背后，接入 Nous Research 的 [Hermes Agent](https://github.com/NousResearch/hermes-agent)，为销售团队提供一个具备技能积累、记忆持久化、RAG 检索能力的 AI 内部助手。

---

## 2. 为什么选 Hermes Agent

| 需求 | 自建 | 接入 Hermes Agent |
|------|:---:|:---:|
| 对话能力 | ✅ | ✅ 内置 |
| Skill 系统（经验积累） | ❌ 需从头写 | ✅ 原生支持 agentskills.io 标准 |
| 跨会话记忆 + FTS5 搜索 | ❌ 需从头写 | ✅ 内置 |
| RAG 知识检索 | ✅ 已有 | ✅ 可选增强 |
| 多轮对话 + 上下文管理 | ✅ | ✅ |
| 维护成本 | 长期 | 上游更新 |

结论：不自建轮子，Hermes Agent 已具备我们需要的全部能力。

---

## 3. 架构设计

```
┌─────────────────────────────────────────────────┐
│              docker-compose up                    │
│                                                  │
│  ┌──────────┐  ┌──────┐  ┌──────────────────┐   │
│  │ backend  │  │  db  │  │  hermes          │   │
│  │ :8000    │  │ :5432│  │  :8642           │   │
│  │ FastAPI  │  │  PG  │  │  API Server      │   │
│  └────┬─────┘  └──────┘  │  + skills/       │   │
│       │                  │  + memory/        │   │
│       │  HTTP            └────────┬──────────┘   │
│       │  localhost:8642           │               │
│       └──────────────────────────┘               │
│       /v1/chat/completions                        │
│       (OpenAI 兼容格式)                            │
└─────────────────────────────────────────────────┘
```

**通信方式：**

| 方向 | 协议 | 说明 |
|------|------|------|
| CRMBOT → Hermes | HTTP `POST /v1/chat/completions` | OpenAI 格式，Bearer token 认证 |
| Hermes → CRMBOT | HTTP Response (SSE 可选) | 流式/非流式回复 |

---

## 4. docker-compose 整合

```yaml
# CRMBOT/docker-compose.yml（新增 hermes 服务）

services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql://sales_agent:xxx@db:5432/sales_agent_db
      - HERMES_API_URL=http://hermes:8642/v1          # 新增
      - HERMES_API_KEY=${HERMES_API_KEY}               # 新增
    depends_on: [db, hermes]                            # 新增依赖

  db:
    image: postgres:14
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: sales_agent
      POSTGRES_PASSWORD: xxx
      POSTGRES_DB: sales_agent_db

  hermes:                                               # 🔥 新增
    image: aoaw123/crmbot-hermes:latest                 # 预打包镜像
    ports: ["8642:8642"]
    environment:
      - API_SERVER_KEY=${HERMES_API_KEY}
      - DEFAULT_MODEL_PROVIDER=deepseek
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./hermes/skills:/home/hermes/.hermes/skills     # 预置技能
      - ./hermes/config.yaml:/home/hermes/.hermes/config.yaml
      - hermes_data:/home/hermes/.hermes/data           # 持久化记忆
    restart: unless-stopped

volumes:
  hermes_data:
```

---

## 5. 预置 Skills

在 `hermes/skills/` 目录下预置销售专用技能，随镜像打包：

```
hermes/
├── skills/
│   ├── crmbot-system.skill.md     # 系统帮助：CRMBot 操作指南
│   ├── sales-analyst.skill.md     # 数据分析：SQL 查询 + 报表解读
│   └── toyota-knowledge.skill.md  # 产品知识：26 款车型参数速查
└── config.yaml                    # Hermes 配置（模型、工具开关）
```

### crmbot-system.skill.md（示例）

```markdown
# CRMBot 系统操作助手

你了解 CRMBot 的全部功能：智能对话、报价单生成、
合同生成、价格谈判、投诉处理、数据报表。

你可以回答关于 CRMBot 使用方法、常见问题、
功能入口的任何问题。
```

### sales-analyst.skill.md（示例）

```markdown
# 销售数据分析师

你可以查询和解读 PostgreSQL 中的销售数据。
数据库结构：
- sessions: 会话表（status, customer_name, updated_at）
- conversations: 对话记录（role, content, created_at）
- chat_session_state: 实时状态

典型查询：会话总数、转化率、活跃客户、月度趋势。
```

---

## 6. 前端实现

### 6.1 Hermes 入口卡片

现在 ConversationList 已有 UI，需加点击事件：

```tsx
// ConversationList.tsx — Hermes 卡片 onClick
onClick={() => navigate('/hermes')}
```

### 6.2 Hermes 状态检测

```tsx
// 页面加载时检测 Hermes 是否在线
useEffect(() => {
  fetch('/api/v1/hermes/health')
    .then(res => res.ok ? setHermesOnline(true) : setHermesOffline(true))
    .catch(() => setHermesOffline(true))
}, [])
```

### 6.3 新页面：HermesChatPage

```tsx
// frontend/src/pages/HermesChatPage.tsx

// 如果 Hermes 离线 → 显示安装引导
if (!hermesOnline) {
  return <HermesInstallGuide />
}

// 在线 → 聊天界面（复用 ChatBubble + ChatInput）
// 消息通过后端 POST → Hermes API
```

### 6.4 安装引导页

```
┌─────────────────────────────────┐
│  📦 Hermes 内部助手未安装         │
│                                 │
│  Hermes 是 AI 数据分析助手，     │
│  帮你查报表、答问题、积累知识。   │
│                                 │
│  [ 一键启动 Docker ]            │
│  docker-compose up hermes       │
│                                 │
│  [ 查看手动安装指南 ]            │
└─────────────────────────────────┘
```

### 6.5 后端代理

```
CRMBOT backend 加一个中转路由：

POST /api/v1/hermes/chat    → 转发到 Hermes API
POST /api/v1/hermes/chat/stream → 流式转发

好处：隐藏 Hermes API key，前端不直接暴露
```

```python
# backend/app/api/v1/hermes.py
@router.post("/chat")
async def hermes_chat(request: ChatRequest):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{HERMES_API_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_SERVER_KEY}"},
            json={
                "model": "hermes-agent",
                "messages": request.messages,
                "stream": False,
            }
        )
    return resp.json()
```

---

## 7. 用户使用流程

```bash
# 1. 克隆项目（和现在一样）
git clone https://github.com/aoaw123/CRMBOT
cd CRMBOT

# 2. 配环境变量
cp .env.example .env
# 填 OPENAI_API_KEY=sk-xxx
# 填 HERMES_API_KEY=$(openssl rand -hex 32)

# 3. 启动（和现在一样，只是多了一个服务）
docker-compose up

# 4. 打开浏览器 localhost:5173
#    点 Hermes 卡片 → 直接聊天
```

**一个命令没多，体验没变。**

---

## 8. 实施步骤

| 步骤 | 内容 | 估时 |
|:---:|------|:---:|
| 1 | 装 Python 3.11 + 本地试跑 Hermes Agent | 15 分钟 |
| 2 | 配置 api_server + DeepSeek，验证对话 | 10 分钟 |
| 3 | 编写 3 个预置 skill 文件 | 15 分钟 |
| 4 | 制作 Docker 镜像（基于 Hermes + skills） | 20 分钟 |
| 5 | 更新 docker-compose.yml 加入 hermes 服务 | 5 分钟 |
| 6 | 后端：新增 `/api/v1/hermes/chat` 代理路由 | 15 分钟 |
| 7 | 前端：HermesChatPage + 安装引导 + 状态检测 | 20 分钟 |
| 8 | 联调测试 + ROADMAP 更新 | 10 分钟 |

**总估：~2 小时**

---

## 9. AI 能力版图（最终形态）

```
CRMBot 智能销售系统
├── 对外：C端客户对话 Agent（DeepSeek + RAG + 文档生成）
├── 对内：Hermes 内部助手（Hermes Agent + skills + 记忆）
│   ├── 📊 销售数据查询
│   ├── 🧠 知识问答
│   ├── 📝 经验积累（skill 自动创建/改进）
│   └── 📄 报表生成
└── 辅助：B端管理面板（接管/投诉/谈判/强意向）
```

---

*最后更新：2026-06-21 01:15*
