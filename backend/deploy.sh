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

# 检查 .env 文件与密钥强度
check_env() {
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            log_warn ".env 文件不存在，从 .env.example 复制..."
            cp .env.example .env
            log_error "请编辑 .env 填写实际配置后重新运行（SECRET_KEY / POSTGRES_PASSWORD 必须替换）"
            exit 1
        fi
        log_error ".env 不存在且无 .env.example 模板"
        exit 1
    fi
    # 拒绝占位密钥（防 JWT 伪造）
    SECRET_KEY_VALUE=$(grep -E '^SECRET_KEY=' .env | tail -n1 | cut -d= -f2- | tr -d '"'"'"'[:space:]')
    PG_PASS_VALUE=$(grep -E '^POSTGRES_PASSWORD=' .env | tail -n1 | cut -d= -f2- | tr -d '"'"'"'[:space:]')
    case "$SECRET_KEY_VALUE" in
        ""|"replace-with-a-random-secret"|"changeme"|"secret")
            log_error "SECRET_KEY 仍是占位值，请用 openssl rand -hex 32 生成强密钥"
            exit 1
            ;;
    esac
    if [ "${#SECRET_KEY_VALUE}" -lt 32 ]; then
        log_error "SECRET_KEY 长度不足 32 字符"
        exit 1
    fi
    case "$PG_PASS_VALUE" in
        ""|"replace-with-a-strong-database-password"|"changeme")
            log_error "POSTGRES_PASSWORD 仍是占位值，请设置强密码"
            exit 1
            ;;
    esac
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
# 只有 start/restart 需要 .env；stop/logs/status 无 .env 也能执行
case "${1:-start}" in
    start)   check_env; start ;;
    restart) check_env; restart ;;
    stop)    stop ;;
    logs)    logs ;;
    status)  status ;;
    *)
        echo "用法: $0 {start|stop|restart|logs|status}"
        exit 1
        ;;
esac
