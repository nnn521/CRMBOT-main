"""Regression tests for generated-document authorization helpers."""

import pytest
from fastapi import HTTPException

from app.api.v1.documents import (
    _assert_document_access,
    _document_names_from_metadata,
    _validate_filename,
)


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class _FakeDb:
    def __init__(self, metadata_rows):
        self.metadata_rows = metadata_rows

    async def execute(self, _statement):
        return _Result(self.metadata_rows)


def test_extracts_only_valid_document_names():
    metadata = {
        "documents": [
            {"file_name": "quote.xlsx"},
            {"file_name": "contract.docx"},
            {"name": "ignored.pdf"},
            "ignored",
        ]
    }
    assert _document_names_from_metadata(metadata) == {"quote.xlsx", "contract.docx"}


@pytest.mark.parametrize("filename", ["../secret.docx", "folder/file.xlsx", "folder\\file.xlsx"])
def test_rejects_path_traversal_variants(filename):
    with pytest.raises(HTTPException) as error:
        _validate_filename(filename)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_customer_can_only_access_document_recorded_in_own_conversation():
    user = {"user_id": 7, "role": "customer"}
    db = _FakeDb([{"documents": [{"file_name": "mine.xlsx"}]}])

    assert await _assert_document_access("mine.xlsx", db, user) == user
    with pytest.raises(HTTPException) as error:
        await _assert_document_access("other.xlsx", db, user)
    assert error.value.status_code == 404
