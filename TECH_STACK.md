# Codyssey — Proposed Tech Stack

## Purpose and scope

This document turns the technology options in [README.md](README.md) and [DESIGN.md](DESIGN.md) into a proposed implementation baseline. The repository includes a starter CLI, shared contracts, a symbol index, and initial supplied-patch validation. See [validation status](docs/VALIDATION.md). Remaining choices describe work to be built.

Version 1 targets Python repositories with pytest tests. Its main interface is a CLI, followed by a REST API and a small dashboard. It produces a patch and supporting test evidence for human review.

## Technology choices

| Layer | Proposed technology | Purpose and rationale |
| --- | --- | --- |
| Core runtime | Python 3.11+ | Matches the target language and provides built-in AST, subprocess, JSON, and SQLite support. |
| Packaging | `pyproject.toml`, standard virtual environment, pip | Defines dependencies and the `codyssey` command without adding a separate build system. Pin dependencies when implementation begins. |
| CLI | Typer and Rich | Exposes repair, benchmark, and run-inspection commands with readable progress output. |
| Contracts and configuration | Pydantic and PyYAML | Validates tasks, patches, run settings, and provider configuration. Read credentials from environment variables. |
| Repository operations | Git CLI through `subprocess` | Clones repositories, checks out exact commits, produces diffs, and checks patch applicability. Pass arguments as lists. |
| Repository analysis | Python `ast`, `pathlib`, and text search | Builds a commit-keyed symbol index and retrieves functions, classes, and nearby code. Call relationships are best-effort static hints. |
| Fault localization | Traceback parsing, keyword ranking, coverage.py | Combines inexpensive signals before optional LLM ranking. Add Ochiai scoring only when per-test coverage is available. |
| Traditional repair | AST-guided operator candidates | Starts with comparison-boundary and boolean-condition mutations at suspicious locations. Each candidate goes through the same validator. |
| Sandbox | Docker Engine through the Docker CLI | Initial executor uses subprocess argument arrays and disposable containers with resource limits and timeouts; the Python SDK is deferred. |
| Test execution | pytest and its JUnit XML output | Supplies structured test identities, outcomes, and durations instead of relying only on console text. |
| Persistence | SQLite and SQLAlchemy | Stores tasks, runs, attempts, test outcomes, and LLM-call metadata on one development machine. |
| Large artifacts | Local filesystem | Stores immutable prompts, responses, patches, and test logs; SQLite stores their paths. |
| LLM integration | OpenAI-compatible client adapter; optional provider-specific adapter | Keeps model selection behind a common interface. Add one hosted provider first and others only when needed. |
| Retry handling | Tenacity | Adds bounded backoff for transient provider failures, subject to the run deadline. |
| REST API | FastAPI and Uvicorn | Serves task submission, run history, details, cancellation, and artifacts. |
| Progress updates | Server-Sent Events (SSE) | Streams run progress from the backend to the dashboard. |
| Dashboard | React, TypeScript, and Vite | Provides submission/history, run details, and benchmark summary screens. Streamlit is a schedule fallback, chosen before UI implementation. |
| Project checks | pytest and Ruff | Verifies core behavior and catches common code/style problems. |
| Collaboration and automation | GitHub issues, pull requests, and GitHub Actions | Tracks ownership and runs checks on pull requests. Docker integration checks require a runner with Docker available. |

## Proposed module layout

```text
pyproject.toml
config.example.yaml
src/codyssey/
  cli.py
  config.py
  contracts.py
  orchestrator.py
  budget.py
  repository/
  localization/
  repair/
  llm/
  sandbox/
  storage/
  reporting/
  api/
tests/
  unit/
  integration/
  fixtures/
web/
benchmarks/
data/                       # generated locally; excluded from Git
```

The API and CLI call the same orchestrator. The dashboard never talks directly to Docker or an LLM provider. Analysis tools read repository content; only the sandbox validator applies candidate patches.

## Execution and storage decisions

- Keep controller dependencies separate from each target repository's dependencies. A target may require an older Python version inside its container.
- Prepare dependencies before test execution. Disable networking during tests, run as a non-root user, and enforce CPU, memory, process, output, and time limits. Do not expose the Docker socket or controller secrets to the target container.
- Restore a clean repository and writable environment for every candidate. Recreating the container from a prepared image is the initial approach; `git checkout .` alone is insufficient.
- Use one local worker initially. API submission persists a queued run; the worker claims it and writes progress events. Persist cancellation requests and mark interrupted work after restart instead of leaving it indefinitely running.
- Use canonical statuses: `queued`, `running`, `verified`, `failed`, `error`, and `cancelled` across the database, CLI, API, and dashboard.
- Keep credentials out of prompts, artifacts, and committed configuration. Store model IDs, provider endpoints, and budgets in configuration rather than application logic.
- Treat token counts and monetary cost separately. Record provider usage when available and label locally calculated cost as estimated. Version the configured price assumptions with each run.

## Deferred choices

Do not add a vector database, distributed queue, agent framework, Kubernetes, or model training to the initial build. Revisit these only when measured limitations justify them. Automatic pushes/merges, multiple target languages, and public multi-user hosting are outside v1.

Provider model availability, pricing, and data policies must be checked before integration or a benchmark. This plan does not depend on a particular model name or free-tier allowance.

See [PROPOSED_PLAN.md](PROPOSED_PLAN.md) for delivery milestones and [TEAM_DIVISION.md](TEAM_DIVISION.md) for ownership.
