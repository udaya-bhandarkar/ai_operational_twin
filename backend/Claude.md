# CLAUDE.md

General-purpose AI agent built with LangGraph + LangChain. Portfolio project: the goal is a
well-engineered agent that demonstrates current, production-grade LangGraph features.

## Working rules
- Work on branch `v2`. Never modify, merge into, or open PRs against `main`.
- Backend only (`backend/`). API changes are fine; do not touch `frontend/`.
- Keep it general — no domain-specific tools, prompts or data. MVP material lives in
  `docs/archive/mvp/` and is reference only.

## Where things are
- `README.md` — architecture, tools, security, API contract, configuration.
- `docs/IMPROVEMENTS.md` — roadmap (what to build next and why).
- `docs/KNOWN_BUGS.md` — open bugs / risks; mark items fixed when resolved.

## Engineering conventions
- Every behavior change gets tests. Tests must not call real APIs: use
  `tests/fakes.py` (`ScriptedChatModel`) to drive the real graph.
- Run `ruff check .` and `pytest` before committing.
- Verify library behavior against the installed version (or docs) before relying on it.
- Security-sensitive tools (SQL, web fetch) keep their defense-in-depth layers; extend tests
  when touching them.
- Update README / KNOWN_BUGS / IMPROVEMENTS in the same change as the code.
