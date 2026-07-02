"""Upload evaluation datasets to LangSmith.

Run once before CI evals — datasets persist in LangSmith between runs.

Usage:
    python scripts/upload_datasets.py
"""
import json
import pathlib
import sys

from langsmith import Client

DATASETS_DIR = pathlib.Path(__file__).parent.parent / "evals" / "datasets" / "v1"

DATASET_FILES: dict[str, pathlib.Path] = {
    "supervisor-v1": DATASETS_DIR / "supervisor.jsonl",
    "research-v1":   DATASETS_DIR / "research.jsonl",
    "ops-v1":        DATASETS_DIR / "ops.jsonl",
}


def _load(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().strip().splitlines() if line.strip()]


def upload(client: Client, name: str, path: pathlib.Path) -> None:
    examples = _load(path)

    try:
        dataset = client.read_dataset(dataset_name=name)
        print(f"  '{name}' already exists in LangSmith — adding examples.")
    except Exception:
        dataset = client.create_dataset(name, description=f"AI Operational Twin — {name}")
        print(f"  Created dataset '{name}'.")

    client.create_examples(
        inputs=[e["inputs"] for e in examples],
        outputs=[e.get("outputs", {}) for e in examples],
        metadata=[e.get("metadata", {}) for e in examples],
        dataset_id=dataset.id,
    )
    print(f"  Uploaded {len(examples)} examples to '{name}'.")


def main() -> None:
    client = Client()
    errors = 0
    for name, path in DATASET_FILES.items():
        if not path.exists():
            print(f"  WARN: {path} not found — skipping '{name}'.", file=sys.stderr)
            errors += 1
            continue
        print(f"Uploading '{name}'...")
        upload(client, name, path)
    print("Done.")
    sys.exit(errors)


if __name__ == "__main__":
    main()
