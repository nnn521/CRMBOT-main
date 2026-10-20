"""Evaluate recorded RAG predictions against versioned source-span labels.

This module never calls a model. Missing predictions count as misses; negative
questions are evaluated separately from positive retrieval metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _unique_strings(values: Any, field: str) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
        raise ValueError(f"{field} must be a list of nonempty strings")
    return list(dict.fromkeys(values))


def evaluate(cases: list[dict], predictions: list[dict]) -> dict:
    """Macro-average evidence recall, with fixed denominators per gold case."""
    if not cases:
        raise ValueError("evaluation cases must not be empty")
    indexed: dict[str, dict] = {}
    for prediction in predictions:
        key = prediction.get("id")
        if not isinstance(key, str) or not key or key in indexed:
            raise ValueError("prediction IDs must be unique nonempty strings")
        indexed[key] = prediction
    seen: set[str] = set()
    rows = []
    for case in cases:
        key = case.get("id")
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError("case IDs must be unique nonempty strings")
        seen.add(key)
        gold = set(_unique_strings(case.get("gold_span_ids"), "gold_span_ids"))
        expected = case.get("expected_status", "answered")
        if expected not in {"answered", "partial", "clarification", "unavailable"}:
            raise ValueError(f"unsupported expected_status for {key}")
        if not gold and expected in {"answered", "partial"}:
            raise ValueError(f"positive question {key} requires gold evidence")
        prediction = indexed.get(key, {})
        candidates = _unique_strings(prediction.get("candidate_span_ids", []), "candidate_span_ids")
        ranked = _unique_strings(prediction.get("ranked_span_ids", []), "ranked_span_ids")
        context = set(_unique_strings(prediction.get("context_span_ids", ranked[:5]), "context_span_ids"))
        first = next((i for i, span in enumerate(ranked[:5], 1) if span in gold), None)
        rows.append({
            "id": key,
            "category": case.get("category", "uncategorized"),
            "missing_prediction": key not in indexed,
            "positive": bool(gold),
            "recall_at_20": len(gold.intersection(candidates[:20])) / len(gold) if gold else None,
            "recall_at_5": len(gold.intersection(ranked[:5])) / len(gold) if gold else None,
            "reciprocal_rank_at_5": (1 / first if first else 0.0) if gold else None,
            "complete_evidence": gold.issubset(context) if gold else None,
            "status_correct": prediction.get("answer_status") == expected,
        })
    extra = set(indexed) - seen
    if extra:
        raise ValueError(f"unexpected prediction IDs: {sorted(extra)}")

    def aggregate(group: list[dict]) -> dict:
        positive = [row for row in group if row["positive"]]
        negative = [row for row in group if not row["positive"]]
        result = {"count": len(group), "positive_count": len(positive), "negative_count": len(negative),
                  "missing_predictions": sum(row["missing_prediction"] for row in group)}
        for metric in ("recall_at_20", "recall_at_5", "reciprocal_rank_at_5", "complete_evidence"):
            result[metric] = sum(row[metric] for row in positive) / len(positive) if positive else None
        result["negative_status_accuracy"] = sum(row["status_correct"] for row in negative) / len(negative) if negative else None
        return result

    return {"overall": aggregate(rows),
            "categories": {category: aggregate([r for r in rows if r["category"] == category])
                           for category in sorted({r["category"] for r in rows})},
            "rows": rows,
            "limitations": ["Retrieval metrics do not measure answer correctness or citation entailment.",
                             "Human review and separate security/failure tests remain required."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    dataset_bytes = args.dataset.read_bytes()
    prediction_bytes = args.predictions.read_bytes()
    report = evaluate(json.loads(dataset_bytes), json.loads(prediction_bytes))
    report["run"] = {"release": args.release, "model": args.model,
                     "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
                     "predictions_sha256": hashlib.sha256(prediction_bytes).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
