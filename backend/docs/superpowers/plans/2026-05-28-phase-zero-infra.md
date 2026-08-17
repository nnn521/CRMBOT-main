# Phase Zero: Infrastructure + C-side Wrap-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Docker containerization, data layer tenant_id预留, contract/proposal docx templates with auto-fill, and car image serving endpoint to CRMBOT.

**Architecture:** Extend existing FastAPI + LangGraph app with Docker deployment, add SQLAlchemy models with tenant_id for multi-tenancy, create docx templates loaded at runtime with python-docx field replacement, and serve car images via a new API endpoint.

**Tech Stack:** Docker, docker-compose, SQLAlchemy 2.0, python-docx, FastAPI StaticFiles

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `Dockerfile` | Create | Python 3.11 container for backend |
| `docker-compose.yml` | Create | Backend + MySQL + Ollama services |
| `deploy.sh` | Create | One-click deployment script |
| `app/models/db.py` | Create | SQLAlchemy Base + engine + session |
| `app/models/tenant.py` | Create | TenantMixin with tenant_id field |
| `app/models/user.py` | Create | User model with tenant_id |
| `app/models/conversation.py` | Create | Conversation model with tenant_id |
| `app/models/config.py` | Create | SystemConfig model with tenant_id |
| `data/industry/` | Create | Industry data directory structure |
| `data/templates/contracts/car_purchase.docx` | Create | 购车合同 template |
| `data/templates/contracts/order_agreement.docx` | Create | 订车协议 template |
| `data/templates/contracts/finance_installment.docx` | Create | 金融分期合同 template |
| `app/services/template_service.py` | Create | Template loading + field auto-fill |
| `data/templates/proposals/proposal.docx` | Create | 提案书 template |
| `app/api/v1/images.py` | Create | Car image serving router |
| `app/main.py` | Modify | Mount images router + static files |
| `requirements.txt` | Modify | Uncomment sqlalchemy, add aiomysql |

---

### Task 1: Docker Containerization — Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# CRMBOT Backend - Docker Image
# Python 3.11 + FastAPI + LangGraph
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 系统依赖（LibreOffice 用于 Excel 公式重计算）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-calc \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存层
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目代码
COPY . .

# 创建必要目录
RUN mkdir -p output data/industry data/templates/contracts data/templates/proposals

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["python", "run.py"]
```

- [ ] **Step 2: Commit**

```bash
git add Dockerfile
git commit -m "feat: add Dockerfile for backend containerization"
```

---

### Task 2: Docker Containerization — docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
# CRMBOT 服务编排
# 包含：Backend API + MySQL + Ollama
version: "3.8"

services:
  # ========== 后端 API 服务 ==========
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: crmbot-backend
    restart: unless-stopped
    ports:
      - "8000:8000"       # HTTP API
      - "8001:8001"       # WebSocket（预留）
    environment:
      - DEBUG=false
      - HOST=0.0.0.0
      - PORT=8000
      - DATABASE_URL=mysql+aiomysql://crmbot:crmbot123@mysql:3306/crmbot
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://api.deepseek.com/v1}
      - DEFAULT_MODEL=${DEFAULT_MODEL:-deepseek-v4-pro}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-bge-m3}
    volumes:
      - ./data:/app/data           # 知识库 + 模板 + 图片
      - ./output:/app/output       # 生成文档输出
      - ./.env:/app/.env:ro        # 环境变量
    depends_on:
      mysql:
        condition: service_healthy
    networks:
      - crmbot-net

  # ========== MySQL 数据库 ==========
  mysql:
    image: mysql:8.0
    container_name: crmbot-mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: crmbot_root_123
      MYSQL_DATABASE: crmbot
      MYSQL_USER: crmbot
      MYSQL_PASSWORD: crmbot123
    ports:
      - "3307:3306"
    volumes:
      - mysql-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - crmbot-net

  # ========== Ollama 本地模型服务 ==========
  ollama:
    image: ollama/ollama:latest
    container_name: crmbot-ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
    networks:
      - crmbot-net

volumes:
  mysql-data:
  ollama-data:

networks:
  crmbot-net:
    driver: bridge
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose with backend + MySQL + Ollama"
```

---

### Task 3: Docker Containerization — deploy.sh

**Files:**
- Create: `deploy.sh`

- [ ] **Step 1: Create deploy.sh**

```bash
#!/bin/bash
# CRMBOT 一键部署脚本
# 用法: bash deploy.sh [start|stop|restart|logs|status]

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查 Docker 是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "docker-compose 未安装"
        exit 1
    fi
}

# 检查 .env 文件
check_env() {
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            log_warn ".env 文件不存在，从 .env.example 复制..."
            cp .env.example .env
            log_warn "请编辑 .env 文件填写实际配置后重新运行"
            exit 1
        fi
    fi
}

# 启动服务
start() {
    log_info "启动 CRMBOT 服务..."
    docker compose up -d --build
    log_info "服务启动完成"
    log_info "API 地址: http://localhost:8000"
    log_info "健康检查: http://localhost:8000/health"
}

# 停止服务
stop() {
    log_info "停止 CRMBOT 服务..."
    docker compose down
    log_info "服务已停止"
}

# 重启服务
restart() {
    stop
    start
}

# 查看日志
logs() {
    docker compose logs -f --tail=100
}

# 查看状态
status() {
    docker compose ps
}

# 主入口
check_docker
check_env

case "${1:-start}" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    logs)    logs ;;
    status)  status ;;
    *)
        echo "用法: $0 {start|stop|restart|logs|status}"
        exit 1
        ;;
esac
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x deploy.sh
git add deploy.sh
git commit -m "feat: add deploy.sh one-click deployment script"
```

---

### Task 4: Data Layer — SQLAlchemy Base + tenant_id Mixin

**Files:**
- Create: `app/models/db.py`
- Create: `app/models/tenant.py`
- Modify: `requirements.txt` (uncomment sqlalchemy, add aiomysql)

- [ ] **Step 1: Uncomment sqlalchemy and add aiomysql in requirements.txt**

Replace the database section in `requirements.txt`:

```
# ========== 数据库 ==========
# PostgreSQL 持久化（LangGraph checkpointer）
psycopg[binary]>=3.1.0      # PostgreSQL 异步驱动
psycopg-pool>=3.1.0         # PostgreSQL 连接池
# redis>=5.0.0              # 会话缓存（预留）
sqlalchemy>=2.0.0           # ORM
aiomysql>=0.2.0             # MySQL 异步驱动
```

- [ ] **Step 2: Create app/models/db.py**

```python
"""
数据库连接管理 - SQLAlchemy 异步引擎 + 会话工厂

提供：
- Base: SQLAlchemy 声明式基类
- get_db: 异步数据库会话依赖注入
- init_db: 建表（开发用，生产用 Alembic）
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


# 异步引擎（仅当 DATABASE_URL 配置了才创建）
engine = None
async_session_factory = None

if settings.database_url:
    # 如果是 postgresql:// 开头，转换为 asyncpg 驱动
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("mysql://"):
        db_url = db_url.replace("mysql://", "mysql+aiomysql://", 1)

    engine = create_async_engine(
        db_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    async_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


async def get_db() -> AsyncSession:
    """
    FastAPI 依赖注入：获取数据库会话

    用法:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    if not async_session_factory:
        raise RuntimeError("数据库未配置，请设置 DATABASE_URL 环境变量")
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """
    初始化数据库表结构（开发用）

    生产环境请使用 Alembic 迁移：
        alembic revision --autogenerate -m "init"
        alembic upgrade head
    """
    if not engine:
        return False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return True
```

- [ ] **Step 3: Create app/models/tenant.py**

```python
"""
多租户 Mixin - 为所有业务表添加 tenant_id 字段

所有需要隔离租户数据的表都继承 TenantMixin。
当前阶段仅做字段预留，后续实现租户过滤中间件。
"""

from sqlalchemy import Column, String, Index
from sqlalchemy.orm import Mapped, mapped_column


class TenantMixin:
    """
    租户混入类

    为模型添加 tenant_id 字段，用于多租户数据隔离。
    当前阶段：字段存在但不做强制过滤。
    后续阶段：添加租户过滤中间件 + Row Level Security。
    """
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        default="default",
        nullable=False,
        index=True,
        comment="租户ID（多租户预留，默认 'default'）"
    )
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt app/models/db.py app/models/tenant.py
git commit -m "feat: add SQLAlchemy base, tenant_id mixin, and db dependencies"
```

---

### Task 5: Data Layer — User / Conversation / Config Models

**Files:**
- Create: `app/models/user.py`
- Create: `app/models/conversation.py`
- Create: `app/models/config.py`

- [ ] **Step 1: Create app/models/user.py**

```python
"""
用户模型 - 存储终端用户信息（C端客户）

字段设计：
- open_id: 微信小程序 openid（唯一标识）
- nickname / phone / avatar: 基本信息
- tenant_id: 租户隔离（继承自 TenantMixin）
"""

from datetime import datetime

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.tenant import TenantMixin


class User(TenantMixin, Base):
    """终端用户表"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    open_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        comment="微信小程序 openid"
    )
    nickname: Mapped[str] = mapped_column(
        String(64), default="", comment="用户昵称"
    )
    phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="手机号"
    )
    avatar_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="头像 URL"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="注册时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self):
        return f"<User(id={self.id}, open_id={self.open_id}, nickname={self.nickname})>"
```

- [ ] **Step 2: Create app/models/conversation.py**

```python
"""
对话记录模型 - 持久化存储聊天历史

与 LangGraph checkpointer 互补：
- checkpointer: 存储 Agent 工作流状态（短期）
- Conversation: 存储完整对话记录（长期，可查询）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.tenant import TenantMixin


class Conversation(TenantMixin, Base):
    """对话记录表"""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="会话ID"
    )
    user_open_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="用户 openid"
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="消息角色: user/assistant/system"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息内容"
    )
    intent: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="识别到的意图"
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="附加元数据"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="消息时间"
    )

    def __repr__(self):
        return f"<Conversation(id={self.id}, session={self.session_id}, role={self.role})>"
```

- [ ] **Step 3: Create app/models/config.py**

```python
"""
系统配置模型 - 运行时可调配置项

存储需要动态调整的配置（如欢迎语、默认折扣等），
与 .env 静态配置互补。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.tenant import TenantMixin


class SystemConfig(TenantMixin, Base):
    """系统配置表"""
    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="配置键"
    )
    config_value: Mapped[str] = mapped_column(
        Text, nullable=False, comment="配置值"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="配置说明"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否启用"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self):
        return f"<SystemConfig(key={self.config_key}, active={self.is_active})>"
```

- [ ] **Step 4: Create app/models/__init__.py to export all models**

Update `app/models/__init__.py` to include new models:

```python
"""
数据模型统一导出

包含：
- Pydantic 模型（API 请求/响应）
- SQLAlchemy 模型（数据库持久化）
"""

# Pydantic 模型（API 层）
from app.models.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    DocumentType,
    IntentAnalysisResult,
    MessageRole,
    UserIntent,
    QuoteParams,
    ProposalParams,
    ContractParams,
    AnalysisParams,
    PresentationParams,
)

# SQLAlchemy 模型（数据库层）
from app.models.user import User
from app.models.conversation import Conversation
from app.models.config import SystemConfig

__all__ = [
    # Pydantic
    "ChatMessage", "ChatRequest", "ChatResponse",
    "DocumentInfo", "DocumentType", "IntentAnalysisResult",
    "MessageRole", "UserIntent",
    "QuoteParams", "ProposalParams", "ContractParams",
    "AnalysisParams", "PresentationParams",
    # SQLAlchemy
    "User", "Conversation", "SystemConfig",
]
```

- [ ] **Step 5: Commit**

```bash
git add app/models/user.py app/models/conversation.py app/models/config.py app/models/__init__.py
git commit -m "feat: add User/Conversation/SystemConfig models with tenant_id"
```

---

### Task 6: Data Layer — Industry Directory

**Files:**
- Create: `data/industry/` directory structure

- [ ] **Step 1: Create industry directory with README**

```bash
mkdir -p /mnt/e/claude/1work/CRMBOT/backend/data/industry
```

Create `data/industry/README.md`:

```markdown
# 行业数据目录

此目录用于存放不同行业的知识库和配置数据。

## 目录结构（规划）

```
industry/
├── automotive/          # 汽车行业（当前）
│   ├── knowledge/       # 行业知识库
│   ├── templates/       # 行业专属模板
│   └── configs/         # 行业配置
├── realestate/          # 房地产行业（预留）
└── finance/             # 金融行业（预留）
```

## 使用说明

每个行业子目录包含该行业专属的：
- 知识库文档（产品信息、FAQ 等）
- 文档模板（合同、报价单等）
- 配置文件（话术、价格规则等）
```

- [ ] **Step 2: Commit**

```bash
git add data/industry/
git commit -m "feat: create industry data directory structure"
```

---

### Task 7: Contract Templates — Create docx Templates

**Files:**
- Create: `data/templates/contracts/car_purchase.docx`
- Create: `data/templates/contracts/order_agreement.docx`
- Create: `data/templates/contracts/finance_installment.docx`

- [ ] **Step 1: Create contract template generator script**

Create `scripts/create_templates.py`:

```python
"""
模板生成脚本 - 一次性运行，生成所有 docx 模板文件

运行: python scripts/create_templates.py
"""

import os
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def create_car_purchase_contract():
    """购车合同模板"""
    doc = Document()

    # 标题
    title = doc.add_heading("购车合同", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(f"合同编号：{{{{contract_no}}}}")
    doc.add_paragraph("")

    # 甲方乙方
    doc.add_paragraph("甲方（卖方）：{{dealer_name}}")
    doc.add_paragraph("地址：{{dealer_address}}")
    doc.add_paragraph("联系电话：{{dealer_phone}}")
    doc.add_paragraph("")
    doc.add_paragraph("乙方（买方）：{{buyer_name}}")
    doc.add_paragraph("身份证号：{{buyer_id_card}}")
    doc.add_paragraph("联系电话：{{buyer_phone}}")
    doc.add_paragraph("")

    doc.add_heading("第一条 车辆信息", level=1)
    table = doc.add_table(rows=6, cols=2, style="Table Grid")
    cells = [
        ("车辆品牌", "{{car_brand}}"),
        ("车型名称", "{{car_model}}"),
        ("车辆颜色", "{{car_color}}"),
        ("车架号（VIN）", "{{vin}}"),
        ("发动机号", "{{engine_no}}"),
        ("车辆价格（元）", "{{car_price}}"),
    ]
    for i, (label, value) in enumerate(cells):
        table.cell(i, 0).text = label
        table.cell(i, 1).text = value

    doc.add_paragraph("")
    doc.add_heading("第二条 付款方式", level=1)
    doc.add_paragraph("付款方式：{{payment_method}}")
    doc.add_paragraph("首付金额：{{down_payment}} 元")
    doc.add_paragraph("贷款金额：{{loan_amount}} 元")
    doc.add_paragraph("")

    doc.add_heading("第三条 交车约定", level=1)
    doc.add_paragraph("预计交车日期：{{delivery_date}}")
    doc.add_paragraph("交车地点：{{delivery_location}}")
    doc.add_paragraph("")

    doc.add_heading("第四条 双方权利义务", level=1)
    doc.add_paragraph("1. 甲方保证所售车辆为全新正品，符合国家质量标准。")
    doc.add_paragraph("2. 甲方负责办理车辆上牌手续（费用由乙方承担）。")
    doc.add_paragraph("3. 乙方应按约定时间支付车款。")
    doc.add_paragraph("4. 乙方应在交车后 7 日内完成验收。")
    doc.add_paragraph("")

    doc.add_heading("第五条 违约责任", level=1)
    doc.add_paragraph("1. 甲方逾期交车，每逾期一日按车价 0.05% 支付违约金。")
    doc.add_paragraph("2. 乙方逾期付款，每逾期一日按欠款 0.05% 支付违约金。")
    doc.add_paragraph("")

    doc.add_heading("第六条 争议解决", level=1)
    doc.add_paragraph("本合同发生争议，双方协商解决；协商不成，提交甲方所在地人民法院诉讼。")
    doc.add_paragraph("")
    doc.add_paragraph("")

    # 签章区
    doc.add_paragraph("甲方（盖章）：                    乙方（签字）：")
    doc.add_paragraph("")
    doc.add_paragraph("日期：{{sign_date}}                日期：{{sign_date}}")

    return doc


def create_order_agreement():
    """订车协议模板"""
    doc = Document()

    title = doc.add_heading("订车协议", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(f"协议编号：{{{{agreement_no}}}}")
    doc.add_paragraph("")

    doc.add_paragraph("甲方（经销商）：{{dealer_name}}")
    doc.add_paragraph("乙方（客户）：{{buyer_name}}")
    doc.add_paragraph("联系电话：{{buyer_phone}}")
    doc.add_paragraph("")

    doc.add_heading("一、预订车辆信息", level=1)
    table = doc.add_table(rows=5, cols=2, style="Table Grid")
    cells = [
        ("车型", "{{car_model}}"),
        ("配置/版本", "{{car_config}}"),
        ("颜色", "{{car_color}}"),
        ("预估价格（元）", "{{estimated_price}}"),
        ("预计到车日期", "{{eta_date}}"),
    ]
    for i, (label, value) in enumerate(cells):
        table.cell(i, 0).text = label
        table.cell(i, 1).text = value

    doc.add_paragraph("")
    doc.add_heading("二、订金条款", level=1)
    doc.add_paragraph("订金金额：{{deposit_amount}} 元")
    doc.add_paragraph("支付方式：{{deposit_payment_method}}")
    doc.add_paragraph("1. 乙方支付订金后，甲方保留车辆名额。")
    doc.add_paragraph("2. 乙方取消订单，订金不予退还。")
    doc.add_paragraph("3. 甲方无法按时交车，双倍返还订金。")
    doc.add_paragraph("")

    doc.add_heading("三、购车流程", level=1)
    doc.add_paragraph("1. 乙方支付订金，签订本协议。")
    doc.add_paragraph("2. 车辆到店后，甲方通知乙方验车。")
    doc.add_paragraph("3. 乙方验车满意后，签订正式购车合同并支付尾款。")
    doc.add_paragraph("")

    doc.add_paragraph("甲方（盖章）：                    乙方（签字）：")
    doc.add_paragraph("")
    doc.add_paragraph("日期：{{sign_date}}                日期：{{sign_date}}")

    return doc


def create_finance_installment_contract():
    """金融分期合同模板"""
    doc = Document()

    title = doc.add_heading("汽车金融分期付款合同", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(f"合同编号：{{{{contract_no}}}}")
    doc.add_paragraph("")

    doc.add_paragraph("甲方（贷款人/金融机构）：{{finance_company}}")
    doc.add_paragraph("乙方（借款人）：{{borrower_name}}")
    doc.add_paragraph("身份证号：{{borrower_id_card}}")
    doc.add_paragraph("联系电话：{{borrower_phone}}")
    doc.add_paragraph("")

    doc.add_heading("第一条 贷款信息", level=1)
    table = doc.add_table(rows=7, cols=2, style="Table Grid")
    cells = [
        ("车辆信息", "{{car_model}} ({{car_color}})"),
        ("车辆总价（元）", "{{total_price}}"),
        ("首付金额（元）", "{{down_payment}}"),
        ("贷款金额（元）", "{{loan_amount}}"),
        ("贷款期数", "{{installments}} 期"),
        ("年利率", "{{annual_rate}}%"),
        ("月供金额（元）", "{{monthly_payment}}"),
    ]
    for i, (label, value) in enumerate(cells):
        table.cell(i, 0).text = label
        table.cell(i, 1).text = value

    doc.add_paragraph("")
    doc.add_heading("第二条 还款方式", level=1)
    doc.add_paragraph("还款方式：等额本息")
    doc.add_paragraph("还款日：每月 {{repayment_day}} 日")
    doc.add_paragraph("还款账户：{{repayment_account}}")
    doc.add_paragraph("")

    doc.add_heading("第三条 车辆抵押", level=1)
    doc.add_paragraph("1. 乙方将所购车辆抵押给甲方作为贷款担保。")
    doc.add_paragraph("2. 贷款还清后，甲方协助办理抵押解除手续。")
    doc.add_paragraph("3. 贷款期间，乙方不得转让、出售抵押车辆。")
    doc.add_paragraph("")

    doc.add_heading("第四条 提前还款", level=1)
    doc.add_paragraph("1. 乙方可申请提前还款，需提前 30 日书面通知甲方。")
    doc.add_paragraph("2. 提前还款不收取违约金（满 12 期后）。")
    doc.add_paragraph("")

    doc.add_heading("第五条 逾期处理", level=1)
    doc.add_paragraph("1. 逾期还款，按日加收逾期金额 0.05% 的罚息。")
    doc.add_paragraph("2. 连续逾期 3 期以上，甲方有权收回车辆。")
    doc.add_paragraph("")

    doc.add_paragraph("甲方（盖章）：                    乙方（签字）：")
    doc.add_paragraph("")
    doc.add_paragraph("日期：{{sign_date}}                日期：{{sign_date}}")

    return doc


def main():
    """生成所有模板文件"""
    base_dir = os.path.join(os.path.dirname(__file__), "..", "data", "templates", "contracts")
    os.makedirs(base_dir, exist_ok=True)

    templates = {
        "car_purchase.docx": create_car_purchase_contract,
        "order_agreement.docx": create_order_agreement,
        "finance_installment.docx": create_finance_installment_contract,
    }

    for filename, creator in templates.items():
        filepath = os.path.join(base_dir, filename)
        doc = creator()
        doc.save(filepath)
        print(f"[OK] 已生成: {filepath}")

    # 提案书模板
    proposal_dir = os.path.join(os.path.dirname(__file__), "..", "data", "templates", "proposals")
    os.path.makedirs(proposal_dir, exist_ok=True)
    doc = Document()
    title = doc.add_heading("购车方案提案书", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"提案编号：{{{{proposal_no}}}}")
    doc.add_paragraph("致：{{customer_name}}")
    doc.add_paragraph("日期：{{proposal_date}}")
    doc.add_paragraph("")
    doc.add_heading("一、客户需求分析", level=1)
    doc.add_paragraph("{{needs_analysis}}")
    doc.add_paragraph("")
    doc.add_heading("二、推荐车型", level=1)
    table = doc.add_table(rows=1, cols=5, style="Table Grid")
    headers = ["车型", "配置", "官方指导价", "优惠方案", "推荐理由"]
    for i, h in enumerate(headers):
        table.cell(0, i).text = h
    doc.add_paragraph("")
    doc.add_heading("三、金融方案", level=1)
    doc.add_paragraph("{{finance_plan}}")
    doc.add_paragraph("")
    doc.add_heading("四、增值服务", level=1)
    doc.add_paragraph("{{value_added_services}}")
    doc.add_paragraph("")
    doc.add_heading("五、购车总费用明细", level=1)
    doc.add_paragraph("{{cost_breakdown}}")
    doc.add_paragraph("")
    doc.add_paragraph("专属顾问：{{sales_rep}}")
    doc.add_paragraph("联系方式：{{sales_phone}}")
    doc.save(os.path.join(proposal_dir, "proposal.docx"))
    print(f"[OK] 已生成: {os.path.join(proposal_dir, 'proposal.docx')}")

    print("\n所有模板生成完成！")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the template generator**

```bash
cd /mnt/e/claude/1work/CRMBOT/backend && python scripts/create_templates.py
```

- [ ] **Step 3: Commit**

```bash
git add data/templates/ scripts/create_templates.py
git commit -m "feat: create contract and proposal docx templates with placeholder fields"
```

---

### Task 8: Template Service — Auto-fill Engine

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/template_service.py`

- [ ] **Step 1: Create app/services/__init__.py**

```python
"""
服务层 - 业务逻辑封装
"""
```

- [ ] **Step 2: Create app/services/template_service.py**

```python
"""
模板服务 - 加载 docx 模板并自动填充字段

工作流程：
1. 从 data/templates/ 加载 docx 模板
2. 替换 {{field_name}} 占位符为实际值
3. 处理表格中的占位符
4. 保存填充后的文档到 output/

用法:
    from app.services.template_service import TemplateService
    svc = TemplateService()
    filepath = await svc.fill_contract("car_purchase", {"buyer_name": "张三", ...})
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

from docx import Document

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("template_service")

# 模板路径映射
TEMPLATE_MAP = {
    # 合同模板
    "car_purchase": "data/templates/contracts/car_purchase.docx",
    "order_agreement": "data/templates/contracts/order_agreement.docx",
    "finance_installment": "data/templates/contracts/finance_installment.docx",
    # 提案书模板
    "proposal": "data/templates/proposals/proposal.docx",
}


class TemplateService:
    """模板填充服务"""

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir

    def _get_template_path(self, template_key: str) -> str:
        """获取模板文件绝对路径"""
        relative = TEMPLATE_MAP.get(template_key)
        if not relative:
            raise ValueError(f"未知模板: {template_key}，可用模板: {list(TEMPLATE_MAP.keys())}")
        full_path = os.path.join(self.base_dir, relative)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"模板文件不存在: {full_path}")
        return full_path

    def _replace_in_paragraph(self, paragraph, data: Dict[str, Any]):
        """
        替换段落中的 {{key}} 占位符

        python-docx 的段落由多个 run 组成，占位符可能被拆分到不同 run 中。
        策略：先拼接全文本替换，再写回第一个 run，清空其余 run。
        """
        full_text = paragraph.text
        if "{{" not in full_text:
            return

        # 替换所有 {{key}} 占位符
        def replacer(match):
            key = match.group(1).strip()
            return str(data.get(key, match.group(0)))  # 未匹配的保留原样

        new_text = re.sub(r"\{\{(\w+)\}\}", replacer, full_text)

        if new_text == full_text:
            return

        # 写回：第一个 run 设置全文，其余 run 清空
        if paragraph.runs:
            paragraph.runs[0].text = new_text
            for run in paragraph.runs[1:]:
                run.text = ""

    def _replace_in_table(self, table, data: Dict[str, Any]):
        """替换表格中所有单元格的占位符"""
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    self._replace_in_paragraph(paragraph, data)

    async def fill_template(
        self,
        template_key: str,
        data: Dict[str, Any],
        output_filename: Optional[str] = None,
    ) -> str:
        """
        填充模板并保存

        Args:
            template_key: 模板标识（如 "car_purchase"）
            data: 填充数据字典，key 为占位符名称
            output_filename: 输出文件名（不含路径），默认自动生成

        Returns:
            生成文件的绝对路径
        """
        template_path = self._get_template_path(template_key)
        doc = Document(template_path)

        # 自动填充标准字段
        auto_fields = {
            "sign_date": datetime.now().strftime("%Y年%m月%d日"),
            "proposal_date": datetime.now().strftime("%Y年%m月%d日"),
            "contract_no": f"C{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "agreement_no": f"A{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "proposal_no": f"P{datetime.now().strftime('%Y%m%d%H%M%S')}",
        }
        merged_data = {**auto_fields, **data}

        # 替换段落中的占位符
        for paragraph in doc.paragraphs:
            self._replace_in_paragraph(paragraph, merged_data)

        # 替换表格中的占位符
        for table in doc.tables:
            self._replace_in_table(table, merged_data)

        # 生成输出路径
        output_dir = os.path.join(self.base_dir, settings.output_dir)
        os.makedirs(output_dir, exist_ok=True)

        if not output_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{template_key}_{timestamp}.docx"

        output_path = os.path.join(output_dir, output_filename)
        doc.save(output_path)

        logger.info(f"[Template] 模板填充完成: {template_key} -> {output_path}")
        return output_path

    async def fill_contract(self, contract_type: str, data: Dict[str, Any]) -> str:
        """
        填充合同模板（便捷方法）

        Args:
            contract_type: 合同类型 (car_purchase / order_agreement / finance_installment)
            data: 合同数据

        Returns:
            生成文件路径
        """
        return await self.fill_template(contract_type, data)

    async def fill_proposal(self, data: Dict[str, Any]) -> str:
        """
        填充提案书模板（便捷方法）

        Args:
            data: 提案书数据

        Returns:
            生成文件路径
        """
        return await self.fill_template("proposal", data)

    def list_templates(self) -> Dict[str, str]:
        """列出所有可用模板"""
        result = {}
        for key, relative in TEMPLATE_MAP.items():
            full_path = os.path.join(self.base_dir, relative)
            result[key] = "可用" if os.path.exists(full_path) else "缺失"
        return result
```

- [ ] **Step 3: Commit**

```bash
git add app/services/
git commit -m "feat: add template service with docx auto-fill engine"
```

---

### Task 9: Car Images — Serving Endpoint

**Files:**
- Create: `app/api/v1/images.py`
- Modify: `app/main.py` (mount images router)

- [ ] **Step 1: Create app/api/v1/images.py**

```python
"""
车型图片 API - 根据车型名称返回对应图片

图片存储在 data/images/{车型名}/ 目录下，
每个车型目录包含一张或多张图片。

端点:
    GET /api/v1/images/{model_name}       - 获取车型图片（返回第一张）
    GET /api/v1/images/{model_name}/list  - 列出车型所有图片
    GET /api/v1/images/                   - 列出所有有图片的车型
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("images_api")

router = APIRouter(prefix="/images", tags=["车型图片"])

# 支持的图片格式
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# 图片根目录
IMAGES_DIR = os.path.join(settings.base_dir, "data", "images")


def _get_image_files(directory: str) -> list[str]:
    """获取目录下所有图片文件，按文件名排序"""
    if not os.path.isdir(directory):
        return []
    files = []
    for f in os.listdir(directory):
        if Path(f).suffix.lower() in IMAGE_EXTENSIONS:
            files.append(f)
    return sorted(files)


@router.get("/")
async def list_models():
    """列出所有有图片的车型"""
    if not os.path.isdir(IMAGES_DIR):
        return {"models": [], "message": "图片目录不存在"}

    models = []
    for name in os.listdir(IMAGES_DIR):
        model_dir = os.path.join(IMAGES_DIR, name)
        if os.path.isdir(model_dir):
            images = _get_image_files(model_dir)
            if images:
                models.append({
                    "name": name,
                    "image_count": len(images),
                    "cover": f"/api/v1/images/{name}",
                })

    return {"models": models, "total": len(models)}


@router.get("/{model_name}")
async def get_model_image(model_name: str):
    """获取车型图片（返回目录下第一张图片）"""
    model_dir = os.path.join(IMAGES_DIR, model_name)

    if not os.path.isdir(model_dir):
        raise HTTPException(status_code=404, detail=f"未找到车型 '{model_name}' 的图片目录")

    images = _get_image_files(model_dir)
    if not images:
        raise HTTPException(status_code=404, detail=f"车型 '{model_name}' 暂无图片")

    image_path = os.path.join(model_dir, images[0])
    return FileResponse(
        image_path,
        media_type=f"image/{Path(images[0]).suffix.lstrip('.')}",
        filename=images[0],
    )


@router.get("/{model_name}/list")
async def list_model_images(model_name: str):
    """列出车型的所有图片"""
    model_dir = os.path.join(IMAGES_DIR, model_name)

    if not os.path.isdir(model_dir):
        raise HTTPException(status_code=404, detail=f"未找到车型 '{model_name}' 的图片目录")

    images = _get_image_files(model_dir)
    return {
        "model": model_name,
        "images": [
            {
                "filename": img,
                "url": f"/api/v1/images/{model_name}/{img}",
            }
            for img in images
        ],
        "total": len(images),
    }


@router.get("/{model_name}/{filename}")
async def get_specific_image(model_name: str, filename: str):
    """获取车型的指定图片"""
    image_path = os.path.join(IMAGES_DIR, model_name, filename)

    if not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="图片不存在")

    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的图片格式")

    return FileResponse(
        image_path,
        media_type=f"image/{ext.lstrip('.')}",
        filename=filename,
    )
```

- [ ] **Step 2: Update app/api/v1/__init__.py to export images_router**

Read the file first, then add the import:

```python
from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.images import router as images_router

__all__ = ["chat_router", "documents_router", "images_router"]
```

- [ ] **Step 3: Update app/main.py to mount images router**

Add the import and router mount in `app/main.py`:

After `from app.api.v1 import chat_router, documents_router`:
```python
from app.api.v1 import chat_router, documents_router, images_router
```

After `app.include_router(documents_router, prefix=settings.api_v1_prefix)`:
```python
app.include_router(images_router, prefix=settings.api_v1_prefix)
```

- [ ] **Step 4: Commit**

```bash
git add app/api/v1/images.py app/api/v1/__init__.py app/main.py
git commit -m "feat: add car model image serving API endpoint"
```

---

### Task 10: Final Verification & Commit

- [ ] **Step 1: Verify all files exist**

```bash
cd /mnt/e/claude/1work/CRMBOT/backend
echo "=== Docker ===" && ls -la Dockerfile docker-compose.yml deploy.sh
echo "=== Models ===" && ls -la app/models/db.py app/models/tenant.py app/models/user.py app/models/conversation.py app/models/config.py
echo "=== Services ===" && ls -la app/services/template_service.py
echo "=== Templates ===" && ls -la data/templates/contracts/*.docx data/templates/proposals/*.docx
echo "=== Images API ===" && ls -la app/api/v1/images.py
echo "=== Industry ===" && ls -la data/industry/
```

- [ ] **Step 2: Verify Python imports work**

```bash
cd /mnt/e/claude/1work/CRMBOT/backend
python -c "
from app.models.db import Base, init_db
from app.models.tenant import TenantMixin
from app.models.user import User
from app.models.conversation import Conversation
from app.models.config import SystemConfig
from app.services.template_service import TemplateService
print('All imports OK')
print(f'Templates: {TemplateService().list_templates()}')
"
```

- [ ] **Step 3: Final commit with all remaining changes**

```bash
git add -A
git status
git commit -m "feat: phase zero complete — Docker, tenant_id, templates, image API"
```
