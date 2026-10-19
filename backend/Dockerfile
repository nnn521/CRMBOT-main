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

# 安装 Python 依赖（镜像源可通过 build-arg 覆盖）
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir -r requirements.txt -i ${PIP_INDEX_URL}

# 复制项目代码（.dockerignore 已排除 .env/日志/输出目录）
COPY . .

# 创建必要目录（数据目录由 compose 卷挂载覆盖）
RUN mkdir -p output data/templates/contracts data/templates/proposals

# 非 root 运行（容器安全基线）
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app/output /app/data
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["python", "run.py"]
