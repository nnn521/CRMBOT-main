"""Complaint handling regression tests without external LLM calls."""

from unittest.mock import patch

import pytest

from app.agents.nodes.intent_node import _fallback_keyword_intent
from app.agents.nodes.response_node import (
    classify_complaint_scene,
    complaint_handler_node,
    is_complaint_reply_compliant,
)
from app.agents.state import create_initial_state
from app.models.chat import UserIntent


TEST_CASES = [
    ("你们的车质量太差了，开了一个月就出问题", "quality"),
    ("你们销售态度太差了，一直不理人", "service"),
    ("说好一个月交车，现在还没交车", "delivery"),
    ("刚买完就降价，这不是欺骗吗", "price"),
    ("售后维修排队排了很久，问题还没解决", "after_sales"),
    ("我要投诉你们整个4S店", "other"),
]


@pytest.mark.parametrize(("message", "expected_scene"), TEST_CASES)
def test_complaint_intent_and_scene(message: str, expected_scene: str):
    analysis = _fallback_keyword_intent(message)
    assert analysis.intent == UserIntent.COMPLAINT_HANDLING
    assert classify_complaint_scene(message) == expected_scene


@pytest.mark.asyncio
@pytest.mark.parametrize(("message", "expected_scene"), TEST_CASES)
async def test_yaml_fallback_produces_compliant_reply(message: str, expected_scene: str):
    state = create_initial_state("complaint-test", message)

    with patch("app.agents.nodes.response_node.ChatOpenAI", side_effect=RuntimeError("LLM offline")):
        result = await complaint_handler_node(state)

    reply = result["sales_response"]
    assert result["metadata"]["complaint_scene"] == expected_scene
    assert is_complaint_reply_compliant(reply)
    assert not any(term in reply for term in ("不负责", "不是我们的问题", "与我们无关"))
