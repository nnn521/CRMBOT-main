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
IMAGES_DIR = os.path.realpath(os.path.join(settings.base_dir, "data", "images"))


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
    image_path = os.path.realpath(os.path.join(IMAGES_DIR, model_name, filename))
    
    # 路径遍历防护：确保解析后的路径在 IMAGES_DIR 内
    if not image_path.startswith(IMAGES_DIR + os.sep):
        logger.warning(f"[Images] 路径遍历攻击尝试: model_name={model_name}, filename={filename}")
        raise HTTPException(status_code=403, detail="禁止访问")

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
