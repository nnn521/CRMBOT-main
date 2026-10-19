"""
预构建 FAISS 向量库脚本。

首次部署时先运行本脚本，避免第一个产品咨询请求在线建索引（会阻塞/失败）：
    python scripts/build_vector_store.py

要求：Ollama 已启动并拉取嵌入模型（默认 bge-m3）：
    ollama pull bge-m3
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import get_logger  # noqa: E402
from app.agents.nodes.knowledge_node import kb_service  # noqa: E402

logger = get_logger("build_vector_store")


async def main() -> int:
    ok = await kb_service.initialize()
    status = kb_service.get_status()
    print("初始化结果:", "成功" if ok else "失败")
    print("知识库路径:", status["knowledge_base_path"])
    print("向量库路径:", status["vector_store_path"])
    print("向量库就绪:", status["initialized"])
    if status["init_error"]:
        print("错误信息:", status["init_error"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
