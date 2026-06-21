from typing import Any


def exact_match_evaluator(run: Any, example: Any) -> dict:
    """Check that the response exactly matches the expected answer (case-insensitive, stripped)."""
    response = ((run.outputs or {}).get("response") or "").strip().lower()
    expected = ((example.outputs or {}).get("answer") or "").strip().lower()
    score = int(bool(expected) and response == expected)
    return {"key": "exact_match", "score": score}
