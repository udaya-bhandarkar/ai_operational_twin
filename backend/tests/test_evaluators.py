"""Unit tests for evaluators — no API calls."""
from types import SimpleNamespace

from evals.evaluators.contains import contains_evaluator
from evals.evaluators.exact_match import exact_match_evaluator


def _run(outputs: dict) -> SimpleNamespace:
    return SimpleNamespace(outputs=outputs)


def _example(outputs: dict) -> SimpleNamespace:
    return SimpleNamespace(outputs=outputs)


class TestContainsEvaluator:
    def test_match(self):
        r = contains_evaluator(_run({"response": "The database has 3 tables"}), _example({"criteria": "table"}))
        assert r["key"] == "contains"
        assert r["score"] == 1

    def test_no_match(self):
        r = contains_evaluator(_run({"response": "I cannot help with that"}), _example({"criteria": "table"}))
        assert r["score"] == 0

    def test_case_insensitive(self):
        r = contains_evaluator(_run({"response": "TABLE exists"}), _example({"criteria": "table"}))
        assert r["score"] == 1

    def test_empty_criteria(self):
        r = contains_evaluator(_run({"response": "anything"}), _example({"criteria": ""}))
        assert r["score"] == 0

    def test_missing_response(self):
        r = contains_evaluator(_run({}), _example({"criteria": "table"}))
        assert r["score"] == 0

    def test_none_outputs(self):
        r = contains_evaluator(SimpleNamespace(outputs=None), _example({"criteria": "table"}))
        assert r["score"] == 0


class TestExactMatchEvaluator:
    def test_match(self):
        r = exact_match_evaluator(_run({"response": "yes"}), _example({"answer": "yes"}))
        assert r["key"] == "exact_match"
        assert r["score"] == 1

    def test_no_match(self):
        r = exact_match_evaluator(_run({"response": "yes"}), _example({"answer": "no"}))
        assert r["score"] == 0

    def test_case_insensitive(self):
        r = exact_match_evaluator(_run({"response": "YES"}), _example({"answer": "yes"}))
        assert r["score"] == 1

    def test_whitespace_stripped(self):
        r = exact_match_evaluator(_run({"response": "  yes  "}), _example({"answer": "yes"}))
        assert r["score"] == 1

    def test_empty_expected(self):
        r = exact_match_evaluator(_run({"response": "yes"}), _example({"answer": ""}))
        assert r["score"] == 0
