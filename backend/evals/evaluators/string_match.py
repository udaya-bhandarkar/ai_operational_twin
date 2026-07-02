"""
String-based evaluator — no model required. Instant and free to run.

Infrastructure note: The evaluation code here is final. The actual questions
and reference answers in evals/datasets/v1/*.jsonl are NOT finalized yet —
they are placeholders until the team submits the real Q&A pairs.

Pattern source: langsmith-sdk python/README.md — StringEvaluator + grading_function.
"""

from langsmith.evaluation import StringEvaluator


def _grading_function(run_input: str, run_output: str, answer: str | None) -> dict:
    """Check whether the reference answer text appears in the AI response (case-insensitive).

    run_input  — the user question (passed by LangSmith from run.inputs)
    run_output — the AI response  (passed by LangSmith from run.outputs)
    answer     — the reference answer from the dataset example (example.outputs)
    """
    if not answer or "PLACEHOLDER" in answer:
        # Dataset not filled in yet — skip this example from scoring.
        return {"score": None, "value": "SKIPPED"}

    score = 1 if answer.strip().lower() in run_output.strip().lower() else 0
    return {
        "score": score,
        "value": "CORRECT" if score else "INCORRECT",
    }


# Instantiated once at module level — no API calls on import.
string_contains_evaluator = StringEvaluator(
    evaluation_name="string_contains",
    grading_function=_grading_function,
)
