# Evaluation protocol

This protocol describes planned experiments; no benchmark results are available.

## Comparison

Run deterministic-only, LLM-only, and hybrid modes on a frozen set of eligible
Python/pytest tasks. Document shared localization/context steps and use the same
validator for every mode. Start with a small pilot before the 20–50 task target.

Each task manifest must identify the repository, base commit, issue, target
environment, evaluator test preparation, required tests, and selection rationale.
For SWE-bench tasks, follow its evaluation conventions and never expose the gold
implementation patch to generation. Separate evaluator-only artifacts from
repair context.

## Records and measurements

Retain configuration, provider/model identifiers, price assumptions, exact task
state, attempts, diffs, prompts/responses, usage, test evidence, and timings.
Track all provider requests, including retries. Report:

- Eligible, attempted, skipped, errored, and verified task counts.
- Verified-task rate with an explicit denominator and per-mode limits.
- Attempts, model calls, input/output tokens, and estimated cost.
- Wall-clock time, patch size, and categorized failure reasons.
- Cost per successful repair, including unsuccessful repair run costs; undefined
  when there are no verified tasks.

Freeze exclusions before final experiments where possible. Preserve raw results
for unstable tests and document their adjudication. Review a sample of passing
patches manually. Disclose test overfitting, public-fix memorization, setup-based
selection bias, provider nondeterminism, and machine differences.

Store generated artifacts under ignored `data/`; publish a reviewed summary and
reproducible manifest when results exist. Do not label placeholder numbers as
measurements or passing tests as proof of general correctness.
