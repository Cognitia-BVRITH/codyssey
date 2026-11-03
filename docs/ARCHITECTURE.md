# Architecture and implementation status

## Available now

The starter package provides shared Pydantic contracts, a `version` command, and
`validate-task PATH` for prepared JSON input. Unit tests cover initial input
constraints and CLI error handling. An intentionally buggy pytest fixture supplies
the first reproduction target.

`localization/index.py` provides `build_index(repo_path)`, which parses every
`.py` file with Python's `ast` module and records each class, function, and method
with its file, line range, signature, and docstring. `SymbolIndex.search_symbol`
looks symbols up by short or qualified name. Unparseable files are listed in
`index.errors` instead of stopping the scan. Nested functions, call relationships,
and per-commit caching are not implemented yet.

Repository ingestion, localization ranking, repair generation, Docker execution,
persistence, the API, and the dashboard are planned and are not implemented.

## Planned flow

```text
CLI / API → orchestrator → baseline reproduction
                         → index / localize / retrieve
                         → deterministic candidates → optional LLM escalation
                         → sandbox validator → results / feedback
                         → artifact store / report
```

The orchestrator owns lifecycle, deadlines, and budgets. Analysis and generation
components return information or patch candidates; the validator alone applies
them in a disposable target environment. CLI and API must share this pipeline.

The validator checks every required test identity against a complete report.
Missing results, skipped required tests, collection errors, timeouts, and process
errors prevent verification. `TestReport` deliberately does not infer success from
an empty result list or a zero exit code. Lifecycle transitions and persistence
must be implemented separately from the data models.

## Shared contracts

`src/codyssey/contracts.py` defines initial task, run, attempt, patch, test, and
provider-response shapes. Task input uses snake_case field names and argument
arrays for test commands. It requires an exact 40-character Git commit, a prepared
environment image, and nonempty, disjoint failing and regression test groups.
These are initial contracts, not a complete security or verification layer.

Repair components return a `RepairOutcome`: either a `PatchCandidate` (diff,
generation method, and the file paths it touches) or a `rejection_reason`,
never both. `usage` records provider tokens and latency even when no candidate
results, so the orchestrator can charge rejected attempts against the budget.
Deterministic candidates report zero usage.

Use `queued`, `running`, `verified`, `failed`, `error`, and `cancelled` consistently.
The older design document omits `cancelled`; this scaffold includes it to match
the planned cancellation API. Progress-event and persisted run-configuration
contracts will be added with orchestration.

## Planning references

- [Technology choices](../TECH_STACK.md)
- [Milestones and acceptance criteria](../PROPOSED_PLAN.md)
- [Team responsibilities](../TEAM_DIVISION.md)
- [Original detailed design](../DESIGN.md)
