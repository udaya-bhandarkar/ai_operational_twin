"""Run evaluation suite against LangSmith datasets.

Usage:
    python -m evals.run_evals              # run evals, print results
    python -m evals.run_evals --gate       # exit 1 if avg score < PASS_THRESHOLD
    python -m evals.run_evals --dataset supervisor-v1  # run single dataset
"""
import logging
import sys
import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langsmith.evaluation import evaluate

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 0.7

_graph: Any = None


def _get_graph() -> Any:
    global _graph
    if _graph is None:
        from agents.supervisor.graph import make_graph
        _graph = make_graph()
    return _graph


def target(inputs: dict) -> dict:
    graph = _get_graph()
    messages = [
        HumanMessage(content=m["content"])
        for m in inputs.get("messages", [])
        if m.get("role") == "user"
    ]
    result = graph.invoke(
        {"messages": messages},
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    response_messages = result.get("messages", [])
    response = response_messages[-1].content if response_messages else ""
    return {"response": response}


def _eval_configs(only_dataset: str | None = None) -> list[dict]:
    from evals.evaluators.contains import contains_evaluator
    from evals.evaluators.llm_judge import correctness_evaluator

    configs = [
        {
            "dataset": "supervisor-v1",
            "evaluators": [contains_evaluator, correctness_evaluator],
            "prefix": "supervisor",
        },
        {
            "dataset": "research-v1",
            "evaluators": [contains_evaluator],
            "prefix": "research",
        },
        {
            "dataset": "ops-v1",
            "evaluators": [contains_evaluator],
            "prefix": "ops",
        },
    ]
    if only_dataset:
        configs = [c for c in configs if c["dataset"] == only_dataset]
    return configs


def run_evals(gate: bool = False, only_dataset: str | None = None) -> bool:
    all_scores: list[float] = []

    for config in _eval_configs(only_dataset):
        logger.info("Running evals: %s", config["dataset"])
        try:
            results = evaluate(
                target,
                data=config["dataset"],
                evaluators=config["evaluators"],
                experiment_prefix=config["prefix"],
                handle_errors=True,
                max_concurrency=2,
            )
            for row in results:
                for er in (row.evaluation_results.results or []):
                    if er.score is not None:
                        all_scores.append(float(er.score))
        except Exception:
            logger.exception("Eval run failed for dataset: %s", config["dataset"])
            if gate:
                return False

    if not all_scores:
        logger.warning("No scores collected — check datasets exist in LangSmith.")
        return not gate

    avg = sum(all_scores) / len(all_scores)
    logger.info("Overall average score: %.2f  (threshold: %.2f)", avg, PASS_THRESHOLD)

    if gate:
        if avg < PASS_THRESHOLD:
            print(
                f"EVAL GATE FAILED: {avg:.2f} < {PASS_THRESHOLD:.2f}",
                file=sys.stderr,
            )
            return False
        print(f"EVAL GATE PASSED: {avg:.2f} >= {PASS_THRESHOLD:.2f}")

    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    gate = "--gate" in sys.argv
    only = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--dataset"),
        None,
    )
    passed = run_evals(gate=gate, only_dataset=only)
    sys.exit(0 if passed else 1)
