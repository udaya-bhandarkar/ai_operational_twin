from openevals.llm import create_llm_as_judge

from config.settings import settings

CORRECTNESS_PROMPT = """\
You are an expert evaluator for an AI operational twin system that monitors \
industrial equipment and databases.

Evaluate whether the AI response correctly addresses the user's question.

User question: {input}
AI response: {output}
Expected content hint: {reference_outputs}

Score the response:
1 = Response correctly addresses the question and aligns with the expected content
0 = Response is incorrect, off-topic, or fails to address the question

Return only the score. Partial credit is not allowed.
"""

# Uses ToolStrategy internally (openevals default) so the judge returns
# a structured score via tool calling. handle_errors=True means a failed
# judge call returns score=None rather than raising, keeping the eval run alive.
correctness_evaluator = create_llm_as_judge(
    prompt=CORRECTNESS_PROMPT,
    model=settings.summarization_model,
    feedback_key="correctness",
    handle_errors=True,
)
