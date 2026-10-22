# Codyssey — Proposed Implementation Plan

## Objective

Build a measurable automated repair pipeline that accepts a repository at a fixed commit and an issue description, reproduces a failure, searches for a repair, and exports a patch with test evidence. Stop when verification succeeds or a configured budget is exhausted.

This is a proposed eight-week schedule for three contributors, assuming regular weekly availability. Milestone acceptance criteria determine readiness; dates can move with team capacity and repository setup difficulty.

## Scope and repair strategy

Start with Python/pytest tasks supplied as structured JSON. Add GitHub issue URL ingestion after the prepared-task workflow works; a URL alone does not define the base commit, environment, or regression tests, so those inputs must also be supplied or resolved explicitly.

The README describes hybrid repair, while the design document emphasizes an LLM patch loop. This plan combines them: try a small, bounded set of deterministic candidates first, then escalate to an LLM with retrieved context and test feedback. Both routes use the same patch and validation contracts. The initial LLM-enabled milestone may run independently while deterministic operators are developed.

## Milestones

| Week | Focus | Deliverables | Acceptance criteria |
| --- | --- | --- | --- |
| 1 | Foundation and shared contracts | Package scaffold, CLI skeleton, validated task/config models, storage schema, fixture repository, initial CI | A prepared task validates; a run record and artifact directory can be created; core checks pass. |
| 2 | Reproduction and verification | Commit checkout, prepared Docker image, baseline execution, patch application, test-result parsing, clean candidate isolation | A known fixture failure reproduces; a supplied correct patch passes; an incorrect patch fails; the next attempt starts clean. |
| 3 | Repository intelligence | AST index/cache, traceback and keyword localization, context retrieval, optional coverage signal | A documented fixture's faulty function appears among the top five suspects; retrieved context fits its configured budget. |
| 4 | First repair loop | One provider adapter, SEARCH/REPLACE parsing, diff generation, attempt feedback, budgets, final report | One fixture completes from task input to validated generated patch; invalid patches, duplicate candidates, timeouts, and provider failures terminate predictably. |
| 5 | Hybrid repair and API | Small deterministic operator set, escalation policy, worker lifecycle, REST endpoints, cancellation, event records | A boundary bug is repaired without an LLM; an unsupported case escalates; API submission returns promptly and cancellation stops active work. |
| 6 | Dashboard and integration | Submission/history, run details, patch/log download, progress stream, benchmark summary shell | A user can submit a prepared task, follow progress, inspect attempts, and download a verified patch through the UI. |
| 7 | Evaluation pilot | Fixed task manifest, benchmark runner, three experiment modes, metric aggregation | A small pilot completes with reproducible task/config records; setup failures are reported separately; all modes use the same validation rules and declared budgets. |
| 8 | Final evaluation and handoff | Target 20–50 eligible tasks, comparison report, failure analysis, setup guide, demo | Report includes success denominators, exclusions, cost/usage, timing, and limitations; a fresh checkout follows documented setup successfully. |

## Milestone details

### Foundation and verification

Agree on `Task`, `Run`, `Attempt`, `PatchCandidate`, `TestReport`, `LLMResponse`, and progress-event contracts before parallel implementation. A task includes repository URL/path, exact base commit, issue text, environment specification, test commands, and expected failing and regression test identities.

Build a tiny fixture repository containing a boundary bug, a failing test, and passing regression tests. Validate the supplied-patch workflow before spending model tokens. Baseline results must show that the expected failure exists and the regression tests pass; otherwise stop with an explicit reproduction or setup reason.

For SWE-bench tasks, define a dataset adapter that prepares the required test patch and repository environment using the benchmark's evaluation conventions. Keep gold implementation patches out of repair prompts and candidate generation. Preserve evaluator tests during candidate resets.

### Repository intelligence and repair

Index files and symbol ranges at the exact base commit. Rank suspects using traceback locations and issue terms; coverage can refine this ranking. Retrieve suspect source, relevant tests, and nearby callers/callees within a context limit.

Generate bounded deterministic mutations only at relevant locations. For LLM repair, require explicit SEARCH/REPLACE blocks, reject ambiguous matches and edits outside the repository, and convert accepted changes into a standard diff. Reject candidate edits to tests and evaluation configuration. Keep feedback short and retain full raw output separately.

Check remaining time, attempt, token, and estimated cost budgets before expensive actions. Bound output tokens, retries, and test execution by remaining allowances. Count all billable provider requests, including format retries and localization calls. Describe limits that depend on provider-reported usage as best-effort rather than promising an exact spending cap.

### Validation and run lifecycle

A candidate is `verified` only when it applies cleanly, all required formerly failing tests pass, and all required regression tests pass. Missing tests, collection errors, skipped required tests, or incomplete output cannot count as success. A passing suite provides evidence for the tested behavior, not proof of general correctness.

Retain both outcomes when rerunning a suspected flaky test. Do not turn a failure into verification based solely on one successful rerun; flag instability and exclude or adjudicate it under a documented benchmark policy.

Persist each attempt and its artifacts, including unsuccessful ones. Cancellation and deadlines must stop child test processes and trigger sandbox cleanup. Reserve final patch download for verified runs; retain unsuccessful candidates as labeled attempt artifacts.

### Evaluation

Compare deterministic-only, LLM-only, and hybrid modes. Define exactly which localization and context steps each mode shares; record provider/model settings, candidate ordering, seeds where supported, and all run limits. Report both outcomes under common resource ceilings and the resources actually consumed.

Track verified-task rate, attempts, model calls, input/output tokens, estimated cost, wall-clock time, patch size, and failure categories. Cost per successful repair uses total experiment cost, including unsuccessful repair runs, divided by verified tasks; report it as undefined if none succeed.

Publish attempted, eligible, skipped, errored, and verified counts. Freeze task selection criteria before the final experiment, and disclose setup-based exclusions. Review a sample of passing patches for test overfitting and acknowledge possible model exposure to public fixes.

## Dependencies and scope controls

The critical path is contracts → sandbox validation → repair loop → benchmark. Repository analysis can progress alongside sandbox work once task and index contracts are agreed. Dashboard work starts with mock responses, then connects to the integrated API.

If time becomes tight, retain the CLI, clean validation, hybrid loop, and evaluation evidence. Reduce dashboard polish, provider count, coverage sophistication, and operator variety first. Report a smaller completed benchmark honestly if the planned task count cannot be reached.

## Completion checklist

- A fresh checkout has documented setup, sample configuration, and a runnable fixture example.
- All repair routes share the same validator and budget accounting.
- Original source repositories remain unchanged; candidate work happens in disposable environments.
- Verified runs include a patch, structured test results, logs, and configuration.
- Failed, cancelled, and infrastructure-error runs have explicit reasons and released resources.
- The evaluation report distinguishes demonstrated behavior from proposed future work.

Technology decisions are in [TECH_STACK.md](TECH_STACK.md); responsibilities and handoffs are in [TEAM_DIVISION.md](TEAM_DIVISION.md).
