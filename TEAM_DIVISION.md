# Codyssey — Three-Member Division of Work

## Team structure

Use Member 1, Member 2, and Member 3 as placeholders until names are assigned. Each member owns implementation, documentation, and relevant verification for their area. All three contribute code and review another member's work.

The division follows the system's main boundaries: execution and evidence, repair intelligence, and orchestration/product integration. It follows the milestones in [PROPOSED_PLAN.md](PROPOSED_PLAN.md) and technology choices in [TECH_STACK.md](TECH_STACK.md).

## Primary ownership

| Member | Area | Responsibilities | Main deliverables |
| --- | --- | --- | --- |
| Member 1 | Repository execution, sandbox, and validation | Repository checkout, target environment preparation, Docker lifecycle, patch application, baseline tests, structured test results, isolation/reset, timeouts, benchmark environment adapter | Reliable supplied-patch validation; clean candidate execution; benchmark task/environment preparation |
| Member 2 | Repository intelligence and repair | AST index, localization, context selection, deterministic operators, provider adapters, prompt construction, SEARCH/REPLACE conversion, duplicate detection | Ranked suspects and bounded context; deterministic and LLM patch candidates; token/latency usage metadata |
| Member 3 | Orchestration, persistence, and interfaces | Shared contracts, run state machine, budgets, SQLite/artifacts, CLI, API/worker, cancellation, events, dashboard, report aggregation | End-to-end run controller; user interfaces; inspectable run history; comparative benchmark reports |

Member 3 has the widest integration surface. To balance workload, Members 1 and 2 own their module-level run summaries and contribute to the relevant run-detail UI sections in week 6. Keep the dashboard minimal, and use the documented Streamlit fallback if the React implementation threatens core delivery.

## Module ownership and review

| Proposed path | Primary owner | Reviewer |
| --- | --- | --- |
| `repository/`, `sandbox/`, test-result validation | Member 1 | Member 2 |
| Benchmark task loading and environment preparation | Member 1 | Member 3 |
| `localization/`, `repair/`, `llm/` | Member 2 | Member 1 |
| `contracts.py`, `config.py` | Member 3 | Members 1 and 2 |
| `orchestrator.py`, `budget.py`, `storage/`, `reporting/` | Member 3 | Member 2 |
| `cli.py`, `api/`, `web/` | Member 3 | Member 1 |
| CI and fixture environment | Member 1 | Member 3 |
| Final experiment and report | Shared; Member 3 coordinates | All members |

Paths describe planned modules, not existing code. Keep tests with the owner of the behavior they verify. Changes to shared contracts require review from both consumers before merge.

## Weekly allocation

| Week | Member 1 | Member 2 | Member 3 |
| --- | --- | --- | --- |
| 1 | Fixture repository, Docker feasibility, CI foundation | AST/index prototype and candidate contract examples | Package scaffold, shared contracts, configuration, SQLite skeleton |
| 2 | Baseline execution, supplied-patch validator, clean reset, timeouts | Patch parsing and rejection rules; fake candidates for integration | CLI validation command, run/attempt persistence, artifact records |
| 3 | Coverage/test evidence adapter; initial benchmark setup trial | Index, traceback/keyword ranking, context retrieval | Orchestrator skeleton, deadline/cancellation contracts, mock API responses |
| 4 | Integrate validator and exercise failure/cleanup paths | One real provider adapter and feedback-based generation | First full repair loop, budget accounting, final report output |
| 5 | Validate mutation candidates; benchmark environment adapter | Deterministic operators, ordering, duplicate rejection, escalation | REST API, single worker, persisted events, cancellation |
| 6 | Test/log UI contribution and sandbox integration checks | Suspects/patch UI contribution and repair error analysis | Submission/history, run detail, event streaming, UI integration |
| 7 | Prepare pilot tasks; classify environment/setup failures | Run operator/localization experiments; analyze repair failures | Batch runner, aggregate metrics, compare experiment modes |
| 8 | Execute assigned benchmark shard; verify setup instructions | Execute assigned benchmark shard; review patch correctness | Execute assigned benchmark shard; assemble report and demo |

## Handoff contracts

### Member 1 → Members 2 and 3

Provide a sandbox/validator interface that prepares the base state, reproduces the baseline, validates a candidate, and cleans up. Return structured outcomes for patch rejection, test failure, timeout, and infrastructure error, along with test identities and artifact paths.

The validator must expose cancellation/deadline handling and preserve evaluator-installed tests across attempts. Member 3 can develop against a fake validator while Docker integration is underway.

### Member 2 → Members 1 and 3

Provide an analysis interface returning ranked suspects and context, plus a repair interface returning a candidate or an explicit no-candidate outcome. Include the generation method, touched paths, usage metadata, and rejection reason where relevant.

Provider and repair components must receive remaining allowances from the orchestrator, report usage from every request, and avoid hidden unbounded retries. Member 1 validates fixture candidates before live-model integration.

### Member 3 → Members 1 and 2

Provide validated task/config models, run IDs, artifact-writing helpers, budget/deadline checks, cancellation signals, and progress-event shapes. Keep API and UI state aligned with the persisted lifecycle.

Publish sample inputs and fake implementations in week 1 so other members can work without waiting for the complete database or API.

## Collaboration process

- Use one issue per deliverable with its owner, dependency, and acceptance criteria.
- Agree on contracts together at the start of week 1. Make later contract changes explicit in the pull request.
- Use short feature branches and reviewed pull requests. Avoid concurrent edits to shared contracts without coordination.
- Hold two brief integration check-ins each week and one weekly fixture demonstration. Discuss blocked interfaces early.
- Merge a working vertical slice regularly: task input → candidate → tests → persisted report.
- Keep module documentation and relevant checks in the same pull request as the implementation.

## Evaluation and final handoff

Freeze the task manifest and experiment configurations together before final runs. Split tasks evenly among members only if machines use compatible prepared environments; otherwise run sequentially on one machine. Each task must run under every comparison mode, with globally unique run IDs and consistent metadata. Avoid concurrent writes to a shared SQLite file across machines; combine exported records and artifacts afterward.

Member 1 audits environment and test evidence, Member 2 audits patch behavior and repair failure categories, and Member 3 audits aggregate calculations and run-status consistency. Each member reviews a sample produced by another member.

The final demonstration should show a deterministic repair, an LLM-assisted attempt, and a failed or budget-limited run with inspectable evidence. Shared completion requires passing integration checks, reproducible setup, the final comparison report, and a clear list of remaining limitations.
