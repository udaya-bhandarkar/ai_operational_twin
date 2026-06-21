from typing import Any


def contains_evaluator(run: Any, example: Any) -> dict:
    """Check that the response contains an expected substring (case-insensitive)."""
    response = ((run.outputs or {}).get("response") or "").lower()
    criteria = ((example.outputs or {}).get("criteria") or "").lower()
    score = int(bool(criteria) and criteria in response)
    return {"key": "contains", "score": score}
