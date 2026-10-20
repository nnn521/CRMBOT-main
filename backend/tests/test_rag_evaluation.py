"""Metric regressions: fixed gold denominators and missing-case handling."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "rag_evaluator", Path(__file__).resolve().parents[2] / "tools" / "evaluate_rag.py"
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
evaluate = _module.evaluate


def test_recall_mrr_and_complete_evidence_have_distinct_meanings():
    report = evaluate(
        [{"id": "a", "gold_span_ids": ["one", "two"]}],
        [{"id": "a", "candidate_span_ids": ["one", "two"],
          "ranked_span_ids": ["noise", "one", "one"], "answer_status": "answered"}],
    )
    assert report["overall"]["recall_at_20"] == 1
    assert report["overall"]["recall_at_5"] == 0.5
    assert report["overall"]["reciprocal_rank_at_5"] == 0.5
    assert report["overall"]["complete_evidence"] == 0


def test_missing_predictions_are_not_silently_dropped():
    report = evaluate([
        {"id": "a", "gold_span_ids": ["one"]},
        {"id": "b", "gold_span_ids": ["two"]},
    ], [{"id": "a", "ranked_span_ids": ["one"], "candidate_span_ids": ["one"]}])
    assert report["overall"]["recall_at_5"] == 0.5
    assert report["overall"]["missing_predictions"] == 1


def test_negative_cases_do_not_inflate_positive_recall():
    report = evaluate([
        {"id": "a", "gold_span_ids": ["one"]},
        {"id": "b", "gold_span_ids": [], "expected_status": "clarification"},
    ], [{"id": "b", "answer_status": "clarification"}])
    assert report["overall"]["recall_at_5"] == 0
    assert report["overall"]["negative_status_accuracy"] == 1


@pytest.mark.parametrize("cases,predictions", [
    ([], []),
    ([{"id": "a", "gold_span_ids": []}], []),
    ([{"id": "a", "gold_span_ids": ["one"]}] * 2, []),
    ([{"id": "a", "gold_span_ids": ["one"]}], [{"id": "b"}]),
    ([{"id": "a", "gold_span_ids": ["one"]}], [{"id": "a"}, {"id": "a"}]),
])
def test_invalid_or_misaligned_evaluation_fails(cases, predictions):
    with pytest.raises(ValueError):
        evaluate(cases, predictions)
