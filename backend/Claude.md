# CLAUDE.md

You are helping design a brand-new multi-agent LLM system.

## Current phase
Architecture planning only.
Do not write implementation code.

## Goal
Design a clean, production-ready architecture for a multi-agent LLM system with:
- supervisor/orchestrator
- specialist subagents
- tool usage
- human-in-the-loop approvals
- provider abstraction
- persistent state/checkpointing
- evaluations
- CI/CD workflows

## Desired qualities
- modular
- testable
- easy to extend
- clear boundaries
- safe tool execution
- reproducible evaluations
- clean deployment path

## Output required
1. System overview
2. Component breakdown
3. Folder structure
4. Agent responsibilities
5. Tool boundaries
6. State/memory design
7. Evaluation plan
8. CI/CD plan
9. Risks and tradeoffs
10. ADR-style decisions

## Constraints
- No implementation code yet
- No premature framework lock-in
- No monolithic files
- No hidden coupling
- No assumptions about old code unless explicitly stated in the docs

## Important
Treat the docs in this repo as the source of truth.
If something is missing, ask for it or mark it as an assumption.