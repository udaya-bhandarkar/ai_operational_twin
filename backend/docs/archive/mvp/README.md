# MVP archive

Material from the project's MVP phase: an agent built for one operational dataset (a PET
recycling operation's machine telemetry), with a React dashboard. The backend has since been
generalized into a general-purpose agent; this folder is kept for history and reference only —
nothing here is used by the current code.

| Path | What it was |
|---|---|
| `Architecture_proposal.md` | Original supervisor + sub-agent architecture plan (phases 1–6) |
| `preliminary_report.md` | MVP project report |
| `requirements.md` | MVP requirements |
| `planning/` | Product brief, feature inventory, non-goals, architecture task/decisions |
| `eval-datasets/` | MVP eval sets: `ops.jsonl` (116 QA-team questions against the June-14 snapshot), legacy `supervisor`/`research` placeholders, and the QA source files (`.rtf`, `.docx`) |

Removed from the backend at the same time (recoverable from git history before the
generalization commit): the dashboard API (`api/dashboard.py`, `api/db.py`), the
domain-specific system prompt and verify-node constants.
