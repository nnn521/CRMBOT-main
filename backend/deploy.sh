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
