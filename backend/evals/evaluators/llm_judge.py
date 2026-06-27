from openevals.llm import create_llm_as_judge
from openevals.prompts import ANSWER_RELEVANCE_PROMPT, CORRECTNESS_PROMPT

from config.settings import settings

_model = settings.summarization_model

# Scores whether the AI response is factually correct relative to a reference answer.
# Requires the dataset example to have an "answer" field in outputs.
# Returns score=True/False + comment.
_correctness = create_llm_as_judge(
    prompt=CORRECTNESS_PROMPT,
    model=_model,
    feedback_key="correctness",
)

# Scores whether the AI response is relevant to the input question.
# Does NOT require a reference answer — works on any dataset.
# Returns score=True/False + comment.
_relevance = create_llm_as_judge(
    prompt=ANSWER_RELEVANCE_PROMPT,
    model=_model,
    feedback_key="relevance",
)


def _question(run) -> str:
    messages = (run.inputs or {}).get("messages", [])
    return messages[-1].get("content", "") if messages else ""


def _response(run) -> str:
    return (run.outputs or {}).get("response", "")


def correctness_evaluator(run, example) -> dict:
    """Compare AI response to the reference answer in example.outputs['answer'].

    Requires dataset examples to have {"outputs": {"answer": "..."}} populated.
    """
    return _correctness(
        inputs=_question(run),
        outputs=_response(run),
        reference_outputs=(example.outputs or {}).get("answer", ""),
    )


def relevance_evaluator(run, example) -> dict:
    """Check that the AI response is relevant to the input question.

    Works without a reference answer — safe to use before Q&A pairs are filled in.
    """
    return _relevance(
        inputs=_question(run),
        outputs=_response(run),
    )
