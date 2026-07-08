"""Smoke tests for evaluator setup — verify evaluators can be imported and
instantiated without making any API calls."""


def test_correctness_evaluator_importable():
    from evals.evaluators.llm_judge import correctness_evaluator
    assert callable(correctness_evaluator)


def test_relevance_evaluator_importable():
    from evals.evaluators.llm_judge import relevance_evaluator
    assert callable(relevance_evaluator)


def test_string_contains_evaluator_importable():
    from evals.evaluators.string_match import string_contains_evaluator
    assert string_contains_evaluator is not None
