"""Vehicle image discovery shared by Agent nodes and API responses."""

import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote


IMAGES_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "images"
POPULAR_MODELS = [
    "凯美瑞", "汉兰达", "RAV4荣放", "卡罗拉", "亚洲龙",
    "赛那SIENNA", "普拉多", "皇冠陆放", "雷凌", "锋兰达",
]
BRAND_WORDS = ("广汽丰田", "一汽丰田", "进口丰田", "丰田汽车", "丰田")
CHINESE_NUMBERS = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _normalize(value: str) -> str:
    value = value.lower()
    for word in BRAND_WORDS:
        value = value.replace(word.lower(), "")
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value)


def requested_image_count(query: str, default: int = 5) -> int:
    arabic = re.search(r"(\d{1,2})\s*款", query)
    if arabic:
        return max(1, min(int(arabic.group(1)), 10))
    chinese = re.search(r"([一二两三四五六七八九十])\s*款", query)
    if chinese:
        return CHINESE_NUMBERS[chinese.group(1)]
    return default


def find_car_images(
    query: str,
    context: Optional[dict[str, Any]] = None,
    *,
    max_results: Optional[int] = None,
    fallback_to_popular: bool = False,
) -> list[str]:
    """Return image endpoint URLs for every model mentioned in the query/context."""
    if not IMAGES_ROOT.is_dir():
        return []

    model_names = sorted(
        (path.name for path in IMAGES_ROOT.iterdir() if path.is_dir()),
        key=len,
        reverse=True,
    )
    searchable = " ".join(
        part for part in (
            query or "",
            str((context or {}).get("car_model", "")),
            str((context or {}).get("product_name", "")),
        ) if part
    )
    normalized_query = _normalize(searchable)
    limit = max_results or requested_image_count(query)

    matched: list[str] = []
    for name in model_names:
        normalized_name = _normalize(name)
        if normalized_name and normalized_name in normalized_query:
            matched.append(name)

    # Common English/short aliases that may not match a Chinese directory exactly.
    aliases = {
        "rav4": "RAV4荣放",
        "bz4x": "bZ4X",
        "chr": "C-HR",
        "sienna": "赛那SIENNA",
        "supra": "SUPRA",
    }
    for alias, model in aliases.items():
        if alias in normalized_query and model in model_names and model not in matched:
            matched.append(model)

    if not matched and fallback_to_popular:
        matched = [name for name in POPULAR_MODELS if name in model_names]

    return [f"/api/v1/images/{quote(name)}" for name in matched[:limit]]
