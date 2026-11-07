# Architecture and implementation status

## Available now

The starter package provides shared Pydantic contracts, a `version` command,
`validate-task PATH` for prepared JSON input, `validate-config PATH` for runtime
settings, and `runs list` / `runs show RUN_ID` for inspecting recorded runs (both
accept `--config` to locate the database; neither creates one). Unit tests cover initial input
constraints and CLI error handling. An intentionally buggy pytest fixture supplies
the first reproduction target.

`localization/index.py` provides `build_index(repo_path)`, which parses every
`.py` file with Python's `ast` module and records each class, function, and method
with its file, line range, signature, and docstring. `SymbolIndex.search_symbol`
looks symbols up by short or qualified name. Unparseable files are listed in
`index.errors` instead of stopping the scan. Nested functions, call relationships,
and per-commit caching are not implemented yet.

`budget.py` provides `BudgetGuard`, which the orchestrator uses to stop a run on the
first exhausted limit: wall-clock time, attempts, total tokens, provider requests, or
estimated cost. Usage from every repair outcome is charged, including outcomes with no
candidate. `remaining()` returns the allowances components should respect for their
next action. Token, request, and cost limits depend on provider-reported usage, so they
are best-effort: one request can overshoot before its usage is recorded. Estimated cost
uses the configured price assumptions and is undefined when none are set.

`storage/` persists state. `RunStore` is a SQLite database (standard-library `sqlite3`)
holding tasks, runs, attempts, test results, and ordered progress events. Every write is
one `BEGIN IMMEDIATE` transaction, so a worker, the CLI, and a future API process can
share the file. Status changes go through `RunStore.transition`, which enforces the
lifecycle table and stamps start/finish times. Cancellation is a persisted request:
a queued run is cancelled at once, while a running run keeps going until its controller
observes the request. `mark_interrupted_runs` ends leftover `running` runs as `error`
after a restart. Each run saves its full configuration, including price assumptions.
Baseline test results are stored as attempt 0. Per-attempt usage is stored with the
attempt, so a repair outcome with no candidate is still charged. An attempt is written
once its outcome is known, so a crash mid-attempt can lose that attempt's usage.

`ArtifactStore` writes immutable files (`open("x")`; no overwrites) under
`<root>/<run_id>/`: `config.json`, `attempt<N>/patch.diff`, and `final_patch.diff`
(verified runs only). The sandbox validator needs a new directory for its evidence, so
baseline evidence goes in `baseline/` and attempt evidence in `attempt<N>/evidence/`;
neither is created by the store. The database keeps paths relative to the artifact root
so exported records stay portable. Run IDs from `new_run_id()` are sortable and unique
across machines. The data model deliberately omits the design document's `LLMCall` and
`RepoIndex` tables until the provider and index code needing them exists.

`orchestrator.py` provides `Orchestrator.run(run_id)`, which takes a queued run to a
terminal status. It reproduces the baseline, then loops: check budgets and cancellation,
ask the repair component for a candidate, store the patch, validate it, persist the
attempt and test results, and feed a short failure summary into the next request. It
depends only on two interfaces: `PatchValidator` (the shape of
`sandbox.validator.Validator.validate`) and `Repairer.propose(RepairRequest)`, which
returns a `RepairOutcome` and receives the remaining allowances. Outcomes map as follows:

| Situation | Run status | Attempt status |
| --- | --- | --- |
| Validator returns `verified` | `verified` (writes `final_patch.diff`) | `tests_passed` |
| Tests fail, patch will not apply, or tests time out | continues | `tests_failed`, `patch_invalid`, `timeout` |
| Repairer returns no candidate, or repeats an earlier diff | continues | `patch_invalid` |
| Any budget is exhausted | `failed` with the limit as reason | none |
| Baseline does not reproduce, validator reports `error`, or the controller raises | `error` | `error` when an attempt was running |
| Cancellation observed | `cancelled` | none |

Every `propose` call is an attempt, so a component that keeps returning nothing still
ends at the attempt limit. Cancellation and deadlines are checked between steps: a
validation already in progress is not interrupted until the validator itself supports
cancellation, and `timeout_seconds` does not yet bound a single validation. The
orchestrator uses budgets only; selecting deterministic versus LLM candidates and
escalating between them (`repair.strategy`, `max_deterministic_candidates`) belongs to
the repair component behind `Repairer`.

`fakes.py` provides `FakeValidator` and `FakeRepairer` with scripted results, so
validation and repair code can be integrated before the real pieces exist. The fake
validator, like the real one, requires a new evidence directory.

Repository ingestion, localization ranking, repair generation, Docker execution,
the API, and the dashboard are planned and are not implemented.

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
the planned cancellation API. `ALLOWED_TRANSITIONS` defines the only legal moves:
`queued` becomes `running` or `cancelled`, `running` becomes any terminal status
(including `error` for work interrupted by a restart), and terminal statuses never
change. Storage enforces this table.

`ProgressEvent` is the payload shared by the CLI, API stream, and dashboard: a
kind, optional attempt number, message, and flat JSON-safe `data`. `StoredEvent`
adds the run ID, a per-run `sequence` starting at 1, and a timestamp.
`RepairUsage.requests` counts billable provider requests so the request budget can
include format retries and localization calls. `Attempt.method` is `None` when a
repair component returned no candidate. Persisted run-configuration contracts are
covered in the configuration document.

## Planning references

- [Technology choices](../TECH_STACK.md)
- [Milestones and acceptance criteria](../PROPOSED_PLAN.md)
- [Team responsibilities](../TEAM_DIVISION.md)
- [Original detailed design](../DESIGN.md)
