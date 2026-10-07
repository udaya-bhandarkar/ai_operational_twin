"""Upload evaluation datasets to LangSmith.

Every `evals/datasets/<name>.jsonl` becomes the LangSmith dataset `<name>`.
Run once before CI evals — datasets persist in LangSmith between runs.

Usage:
    python scripts/upload_datasets.py
"""
import json
import pathlib
import sys

from langsmith import Client

DATASETS_DIR = pathlib.Path(__file__).parent.parent / "evals" / "datasets"


def dataset_files() -> dict[str, pathlib.Path]:
    return {p.stem: p for p in sorted(DATASETS_DIR.glob("*.jsonl"))}


def _load(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().strip().splitlines() if line.strip()]


def upload(client: Client, name: str, path: pathlib.Path) -> None:
    examples = _load(path)

    try:
        dataset = client.read_dataset(dataset_name=name)
        print(f"  '{name}' already exists in LangSmith — adding examples.")
    except Exception:
        dataset = client.create_dataset(name, description=f"Agent eval dataset — {name}")
        print(f"  Created dataset '{name}'.")

    client.create_examples(
        inputs=[e["inputs"] for e in examples],
        outputs=[e.get("outputs", {}) for e in examples],
        metadata=[e.get("metadata", {}) for e in examples],
        dataset_id=dataset.id,
    )
    print(f"  Uploaded {len(examples)} examples to '{name}'.")


def main() -> None:
    files = dataset_files()
    if not files:
        print(f"No *.jsonl datasets in {DATASETS_DIR} — nothing to upload.", file=sys.stderr)
        sys.exit(1)
    client = Client()
    for name, path in files.items():
        print(f"Uploading '{name}'...")
        upload(client, name, path)
    print("Done.")


if __name__ == "__main__":
    main()
