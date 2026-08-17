# CRMBOT — 基于多Agent协作的智能销售机器人系统

---

## 📖 项目简介

CRMBOT 是一款面向多销售场景的 **多 Agent 协作式智能销售辅助系统**，以售卖丰田品牌汽车为切入点，利用大语言模型（DeepSeek）和 LangGraph 工作流引擎，将销售全流程中的重复性认知劳动——产品查询、报价核算、文档生成、谈判策略——全部自动化处理。

### 🎯 我们解决什么问题

传统汽车销售流程中，一个销售顾问平均每天花费 **60% 以上** 的时间在非直接销售事务上：

- 🔍 查产品参数、库存、优惠政策
- 📊 手工制作报价单、购车方案
- 📝 起草合同、订车协议
- 💰 应对客户议价、投诉跟进

CRMBOT 将这些环节无缝集成到一个对话式 AI 助手中，让销售团队只需 **用自然语言描述需求**，系统自动完成知识检索、推理和文档输出，把时间还给真正创造价值的事——**与客户建立信任和关系**。

### 💡 创新亮点

| 维度 | 创新点 |
|------|--------|
| 🏗️ **架构创新** | 基于 LangGraph 的有状态多 Agent 流水线，支持条件路由、断点续跑和会话持久化 |
| 🧠 **RAG 增强** | FAISS 本地向量检索 + 结构化产品目录，零延迟、零外部依赖，精准定位车型信息 |
| 📄 **文档自动化** | 自然语言驱动一键生成报价单(Excel)、购车合同(Word)、定制提案(Word) |
| 🗣️ **销售智能** | 价格谈判话术策略、投诉分级处理方案，让初级销售也能应对复杂场景 |
| 🔌 **可扩展架构** | 行业配置化设计（`industry/auto|medic|gaming`），同一代码库适配不同行业 |
| 🏢 **企业级基因** | PostgreSQL 持久化、Docker 一键部署、WebSocket 预留，面向真实生产环境 |

---

## 🧠 核心能力

### 🗣️ 智能意图识别

系统能精准区分 17 种用户意图，涵盖销售全场景：

| 意图类别 | 具体场景 |
|----------|----------|
| 产品咨询 | 车型参数、价格查询、配置对比、库存查询 |
| 文档生成 | 报价单、购车合同、金融分期合同、定制提案书 |
| 销售话术 | 价格谈判策略、竞品对比话术、增值服务推荐 |
| 客户管理 | 投诉分级处理、客户意向判断、跟进建议 |

### 📚 RAG 知识检索

- **知识库**：丰田全系车型产品目录（凯美瑞、亚洲龙、雷凌、RAV4、汉兰达等 26 款车型，133 条结构化数据）
- **向量化**：Ollama `bge-m3` 本地嵌入模型，无需云端费用
- **检索**：FAISS 向量数据库，毫秒级语义检索
- **增强回答**：检索结果 + LLM 合成 = 精准、上下文丰富的产品回答

### 📄 文档自动生成

| 文档类型 | 格式 | 模板数量 | 说明 |
|----------|------|:---:|------|
| 报价单 | Excel (.xlsx) | 1 | 自动填充客户信息、车型配置、价格明细 |
| 购车合同 | Word (.docx) | 1 | 标准购车合同，关键字段自动填充 |
| 订车协议 | Word (.docx) | 1 | 订车/定金协议模板 |
| 金融分期合同 | Word (.docx) | 1 | 分期付款方案合同 |
| 定制提案书 | Word (.docx) | 1 | 企业采购/大客户定制提案 |

> 所有文档通过自然语言对话即可生成，无需手动填写任何字段。生成后一键下载。

### 🤝 多 Agent 协作流水线

```
用户输入 → 意图识别 → RAG知识检索 → 参数提取 → 文档生成 → 响应合成 → 输出
                ↓              ↓              ↓
           谈判/投诉分支    知识合成        模板填充
```

每个 Agent 专注于单一职责，通过 LangGraph 的**条件边**和**状态管理**协同工作，实现复杂销售场景的自动化处理。

### 🖼️ 车型图片展示

客户询问任何丰田车型时，系统自动附带对应车型图片，增强客户体验。

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      前端 (React)                        │
│  ChatBubble · ChatInput · DocumentCard · DownloadButton  │
│  Zustand 状态管理 · useChat Hook · Tailwind CSS 黑色主题  │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP POST /api/v1/chat
                      ▼
┌─────────────────────────────────────────────────────────┐
│                    后端 (FastAPI)                         │
│  /api/v1/chat · /api/v1/documents · /api/v1/images      │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                LangGraph 工作流引擎                       │
│                                                          │
│   ┌──────────┐   ┌───────────┐   ┌──────────────────┐  │
│   │ 意图识别  │──▶│ 知识检索   │──▶│  文档参数提取     │  │
│   │  Agent   │   │ (RAG+FAISS)│   │     Agent        │  │
│   └──────────┘   └───────────┘   └────────┬─────────┘  │
│        │                                   │            │
│        │ 谈判/投诉分支                      ▼            │
│        ▼                           ┌──────────────┐    │
│   ┌──────────┐                     │  文档生成      │    │
│   │ 销售响应  │◀────────────────────│  (openpyxl/   │    │
│   │  Agent   │                     │  python-docx)  │    │
│   └──────────┘                     └──────────────┘    │
│                                                          │
│   持久化: PostgreSQL (AsyncPostgresSaver)                 │
└─────────────────────────────────────────────────────────┘
```

### 技术选型理由

| 技术 | 用途 | 选型原因 |
|------|------|----------|
| **LangGraph** | Agent 工作流编排 | 有状态、支持条件分支、断点续跑，比 LangChain 更适合多步骤协作 |
| **FastAPI** | Web 框架 | 异步高性能、原生 OpenAPI 文档、流式响应支持 |
| **FAISS** | 向量检索 | Meta 出品，本地零延迟，无需外部向量数据库费用 |
| **PostgreSQL** | 持久化存储 | LangGraph Checkpointer 原生支持，会话状态 + 业务数据统一管理 |
| **Ollama** | 本地嵌入模型 | `bge-m3` 支持中英文语义检索，可离线使用 |
| **DeepSeek** | 大语言模型 | 高性价比，中文理解能力优秀 |
| **React + Vite** | 前端框架 | 热重载开发体验、Tailwind CSS 快速样式迭代 |
| **Zustand** | 前端状态管理 | 轻量、无模板代码，比 Redux 更适合中型应用 |

---

## 🚀 快速开始

### 环境要求

| 组件 | 版本 | 是否必需 |
|------|------|:---:|
| Python | 3.10+ | ✅ |
| Node.js | 18+ | ✅ |
| PostgreSQL | 16+ | ✅（认证、会话与工作流持久化） |
| Ollama | 最新版 | 可选（RAG 向量化依赖） |

### 1️⃣ 克隆项目

```bash
git clone git@github.com:aoaw123/CRMBOT.git
cd CRMBOT
```

### 2️⃣ 后端启动

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填写必要配置

# 启动服务
python run.py
# 或：uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000/docs 查看 Swagger API 文档。

### 3️⃣ 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问 http://localhost:5173 即可使用。

### 4️⃣ Docker 一键部署（推荐）

```bash
cd backend

# 编辑 .env，至少替换 API Key、SECRET_KEY、数据库密码和管理员密码
cp .env.example .env

# 启动全部服务（backend + PostgreSQL + Ollama）
docker compose up -d
```

### ⚙️ 环境变量配置

```bash
# .env 关键配置项
OPENAI_API_KEY=sk-xxx            # DeepSeek/OpenAI 兼容 API Key（必填）
OPENAI_BASE_URL=https://api.deepseek.com/v1
DEFAULT_MODEL=deepseek-chat
SECRET_KEY=随机长字符串          # JWT 签名密钥（必填）
DATABASE_URL=postgresql://...    # PostgreSQL 连接串（必填）
OLLAMA_BASE_URL=http://localhost:11434  # Ollama 地址（可选）
```

---

## 📡 API 接口

### 接口总览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/chat` | POST | 核心对话接口 |
| `/api/v1/chat/sessions` | GET | 会话列表 |
| `/api/v1/chat/ws/{session_id}` | WS | WebSocket 实时通信 |
| `/api/v1/auth/login` | POST | 用户登录（JWT） |
| `/api/v1/auth/register` | POST | 用户注册 |
| `/api/v1/documents/{filename}` | GET | 下载生成的文档 |
| `/api/v1/images/{model}` | GET | 获取指定车型图片 |
| `/api/v1/images/` | GET | 列出所有车型 |
| `/api/v1/hermes/health` | GET | Hermes 助手健康检查 |
| `/api/v1/hermes/chat/stream` | POST | Hermes SSE 流式对话 |
| `/api/v1/sessions` | GET | 管理后台会话列表 |
| `/health` | GET | 健康检查 |

### 对话接口

**请求：**

```json
POST /api/v1/chat
{
  "session_id": "user_001",
  "message": "帮我生成一份凯美瑞2.5G豪华版的报价单，客户张三科技",
  "context": {
    "sales_rep_name": "小李"
  }
}
```

**响应：**

```json
{
  "session_id": "user_001",
  "reply": "好的，已为张三科技生成凯美瑞 2.5G 豪华版的报价单，包含以下内容：\n• 车型：凯美瑞 2.5G 豪华版\n• 指导价：20.98万元\n• 落地价：约23.5万元\n\n报价单已生成，请点击下方按钮下载。",
  "intent": "quote_generation",
  "documents": [
    {
      "file_name": "报价单_张三科技_20260605.xlsx",
      "file_path": "/api/v1/documents/报价单_张三科技_20260605.xlsx"
    }
  ],
  "suggested_actions": ["下载报价单", "发送给客户", "生成购车合同"],
  "images": ["/api/v1/images/凯美瑞"]
}
```

---

## 📂 项目结构

```
CRMBOT/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI 应用入口
│   │   ├── core/
│   │   │   ├── config.py             # 全局配置（Pydantic Settings）
│   │   │   └── logging.py            # 结构化日志配置
│   │   ├── models/                   # Pydantic Schema + SQLAlchemy 模型
│   │   ├── api/v1/
│   │   │   ├── chat.py               # 对话路由（核心入口）
│   │   │   ├── sessions.py           # 会话管理路由
│   │   │   ├── auth.py               # 认证路由（JWT）
│   │   │   ├── documents.py          # 文档下载路由
│   │   │   ├── images.py             # 车型图片路由
│   │   │   ├── hermes.py             # Hermes 内部助手代理
│   │   │   └── ws.py                 # WebSocket 实时通信
│   │   ├── agents/
│   │   │   ├── state.py              # LangGraph SalesState 状态定义
│   │   │   ├── graphs/
│   │   │   │   └── sales_graph.py    # 主工作流图（条件路由 + 持久化）
│   │   │   └── nodes/
│   │   │       ├── intent_node.py    # 意图识别（17种路由）
│   │   │       ├── knowledge_node.py # RAG 检索 + 知识合成
│   │   │       ├── document_nodes.py # 文档参数提取 + 生成
│   │   │       ├── response_node.py  # 销售响应生成（丰田销售人设）
│   │   │       └── multimodal_node.py# 多模态处理（储备）
│   │   └── services/                 # 模板渲染等服务层
│   ├── data/
│   │   ├── knowledge_base/           # 产品目录 Markdown 知识库
│   │   ├── templates/
│   │   │   ├── contracts/            # 合同 docx 模板（4个）
│   │   │   └── proposals/            # 提案书 docx 模板（1个）
│   │   ├── images/                   # 车型图片（26款）
│   │   ├── industry/                 # 行业配置（auto/medic/gaming）
│   │   └── vector_store/             # FAISS 向量索引
│   ├── output/                       # 生成的文档输出目录
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── run.py
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx                   # 根组件
│   │   ├── components/
│   │   │   ├── ChatBubble.tsx        # 聊天气泡（支持文本/图片/文档卡片）
│   │   │   ├── ChatInput.tsx         # 输入框组件
│   │   │   ├── ChatContent.tsx       # 聊天内容区（客户 + Hermes 分流）
│   │   │   ├── ConversationList.tsx   # 会话列表（含 Hermes 入口）
│   │   │   ├── HermesChatArea.tsx    # Hermes 行内聊天组件
│   │   │   ├── AuthGuard.tsx         # 登录鉴权守卫
│   │   │   ├── DownloadButton.tsx    # 文档下载按钮
│   │   │   └── ui/                   # 通用 UI 组件（Button/Card/Input）
│   │   ├── hooks/
│   │   │   └── useChat.ts            # 聊天逻辑 Hook
│   │   ├── stores/
│   │   │   ├── chat.ts               # 客户聊天状态管理
│   │   │   └── hermes.ts             # Hermes 助手状态管理
│   │   ├── api/
│   │   │   ├── chat.ts               # 聊天 API 封装
│   │   │   └── hermes.ts             # Hermes SSE API 封装
│   │   ├── types/                    # TypeScript 类型定义
│   │   ├── layouts/
│   │   │   └── ChatLayout.tsx        # B 端管理布局
│   │   ├── pages/                    # 路由页面
│   │   └── lib/                      # 工具函数
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── package.json
├── docs/
│   └── ROADMAP.md                    # 详细开发路线图
├── .claude/                          # Claude Code 技能配置
├── .gitignore
└── README.md
```

---

## 🗺️ 开发进度

| 阶段 | 状态 | 内容 |
|------|:---:|------|
| **阶段零** | ✅ | 基础设施 — Docker 容器化、数据层设计、合同/提案模板（4+1）、26款车型图、报价单生成、文档下载、PostgreSQL 持久化 |
| **阶段一** | ✅ | 核心功能 — 价格谈判策略引擎、投诉分级处理、前端图片展示优化 |
| **阶段二** | ✅ | 聚合客户端 — 多会话管理、WebSocket 实时通信、B/C 端消息收发、销售接管（AI↔人工切换） |
| **阶段三** | ✅ | AI 辅助 — 价格谈判、投诉升级处理、强意向提醒 |
| **阶段四** | ✅ | Hermes 内部助手集成 — DeepSeek 驱动的行内聊天 AI 助手、SSE 流式对话、Dashboard 数据看板 |
| **阶段五** | 🔜 | 打磨部署 — 防飞单机制、多租户架构、微信渠道接入、生产环境部署 |

> 📄 详细规划与里程碑：[docs/ROADMAP.md](./docs/ROADMAP.md)

---

## 👥 团队

本项目为桂林电子科技大学学生团队独立开发，采用全栈协作模式，覆盖以下领域：

- 🏗️ **系统架构设计** — LangGraph 工作流编排、Agent 协作机制、PostgreSQL 持久化方案
- 🎨 **前端开发** — React + TypeScript、聊天界面、文档预览下载、响应式布局
- 🧠 **Agent 开发** — 意图识别算法、RAG 检索优化、知识合成策略
- 📄 **文档生成** — openpyxl 报价单、python-docx 合同/提案模板设计与自动填充
- 📚 **知识工程** — 丰田全系产品数据采集、结构化、向量化处理
- 🐳 **DevOps** — Docker 容器化、docker-compose 编排、环境配置管理

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **LLM** | DeepSeek (deepseek-v4-pro) |
| **Agent 框架** | LangGraph 0.0.40+ |
| **后端框架** | FastAPI + Uvicorn |
| **向量数据库** | FAISS (CPU) |
| **本地嵌入** | Ollama + bge-m3 |
| **关系数据库** | PostgreSQL 16 (psycopg 3) |
| **前端框架** | React 18 + TypeScript |
| **构建工具** | Vite |
| **样式方案** | Tailwind CSS（黑色主题） |
| **状态管理** | Zustand |
| **文档生成** | openpyxl · python-docx · python-pptx · reportlab |
| **容器化** | Docker + docker-compose |

---

## 🤝 贡献指南

本项目为学术竞赛项目，暂不接受外部贡献。如有建议或问题，欢迎提交 Issue。

---

## 📄 许可证

本项目为大创学术项目，仅供学习和研究使用。
