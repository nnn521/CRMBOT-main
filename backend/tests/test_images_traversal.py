"""车型图片接口路径穿越防护。"""

import pytest
from fastapi import HTTPException

from app.api.v1.images import _resolve_model_dir


def test_accepts_plain_model_name():
    resolved = _resolve_model_dir("凯美瑞")
    assert resolved.endswith("凯美瑞")


def test_rejects_traversal_variants():
    for bad in ("..", "../..", "a/b", "a\\b", "..\\..\\secret"):
        with pytest.raises(HTTPException):
            _resolve_model_dir(bad)


def test_rejects_empty():
    with pytest.raises(HTTPException):
        _resolve_model_dir("")
