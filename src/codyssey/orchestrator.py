"""Run controller: reproduce the failure, then loop propose -> validate within budgets.

The orchestrator owns lifecycle, budgets, cancellation, and persistence. It never applies
patches or calls providers itself: it depends on two small interfaces, `PatchValidator`
(sandbox/validation) and `Repairer` (analysis and repair), so each can be developed and
tested independently of the others. See `codyssey.fakes` for scripted implementations.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from codyssey.budget import BudgetGuard, BudgetLimits, Remaining
from codyssey.contracts import (
    Attempt,
    EventKind,
    PatchCandidate,
    ProgressEvent,
    RepairOutcome,
    Run,
    RunStatus,
    Task,
    TestReport,
)
from codyssey.storage import ArtifactStore, RunStore

MAX_FEEDBACK_CHARS = 2000
MAX_FEEDBACK_TESTS = 10

# Validator statuses that end an attempt normally, mapped to the stored attempt status.
ATTEMPT_STATUS = {
    "verified": "tests_passed",
    "patch_invalid": "patch_invalid",
    "tests_failed": "tests_failed",
    "timeout": "timeout",
}


class ValidationLike(Protocol):
    """Shape of `codyssey.sandbox.validator.ValidationOutcome`."""

    @property
    def status(self) -> str: ...

    @property
    def report(self) -> TestReport | None: ...

    @property
    def reason(self) -> str | None: ...


class PatchValidator(Protocol):
    """Shape of `codyssey.sandbox.validator.Validator.validate`.

    `artifacts` must not exist yet. Without a candidate the call reproduces the baseline
    (`reproduced` on success); with one it returns `verified`, `patch_invalid`,
    `tests_failed`, `timeout`, or `error` (infrastructure).
    """

    def validate(
        self, task: Task, artifacts: Path, candidate: PatchCandidate | None = None
    ) -> ValidationLike: ...


@dataclass(frozen=True)
class RepairRequest:
    task: Task
    attempt_number: int
    feedback: str | None  # short summary of the previous attempt's failure
    remaining: Remaining  # allowances the repairer must stay within


class Repairer(Protocol):
    """Produces a candidate or an explicit no-candidate outcome, always reporting usage."""

    def propose(self, request: RepairRequest) -> RepairOutcome: ...


def summarize_failure(status: str, reason: str | None, report: TestReport | None) -> str:
    """Short feedback for the next attempt; full evidence stays in the artifacts."""
    parts = []
    if status == "timeout":
        parts.append("Tests timed out; the change may cause an infinite loop or very slow code.")
    if reason:
        parts.append(reason)
    if report is not None:
        failing = [r.node_id for r in report.results if r.outcome != "passed"]
        if failing:
            parts.append("Not passing: " + ", ".join(failing[:MAX_FEEDBACK_TESTS]))
    return (" ".join(parts) or status)[:MAX_FEEDBACK_CHARS]


class Orchestrator:
    def __init__(
        self,
        store: RunStore,
        artifacts: ArtifactStore,
        validator: PatchValidator,
        repairer: Repairer,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.store = store
        self.artifacts = artifacts
        self.validator = validator
        self.repairer = repairer
        self._clock = clock

    def run(self, run_id: str) -> Run:
        """Execute a queued run to a terminal status and return it.

        Raises `InvalidTransition` if the run is not queued (for example, it was cancelled
        while waiting). Any other failure after start ends the run as `error`.
        """
        run = self.store.get_run(run_id)
        task = self.store.get_task(run.task_id)
        config = self.store.get_run_config(run_id)
        guard = BudgetGuard(BudgetLimits.from_config(config), clock=self._clock)
        self.store.transition(run_id, RunStatus.RUNNING)
        guard.start()
        self._emit(run_id, ProgressEvent(kind=EventKind.RUN_STARTED))
        try:
            self.artifacts.write_config(run_id, config.model_dump_json(indent=2))
            status, reason = self._execute(run_id, task, guard)
        except Exception as exc:  # any controller failure must end the run, not leave it running
            status = RunStatus.ERROR
            reason = f"unexpected controller error: {type(exc).__name__}: {exc}"
        finished = self.store.transition(run_id, status, reason)
        data = {
            "status": status.value,
            "attempts": guard.attempts_made,
            "tokens": guard.tokens_used,
            "requests": guard.requests_made,
        }
        message = reason or ""
        self._emit(run_id, ProgressEvent(kind=EventKind.RUN_FINISHED, message=message, data=data))
        return finished

    def _execute(self, run_id: str, task: Task, guard: BudgetGuard) -> tuple[RunStatus, str | None]:
        if self._cancelled(run_id):
            return RunStatus.CANCELLED, "cancellation requested"

        baseline = self.validator.validate(task, self.artifacts.baseline_dir(run_id))
        if baseline.report is not None:
            self.store.add_test_results(run_id, 0, baseline.report.results)
        if baseline.status != "reproduced":
            detail = f": {baseline.reason}" if baseline.reason else ""
            return RunStatus.ERROR, f"baseline not reproduced ({baseline.status}){detail}"
        self._emit(run_id, ProgressEvent(kind=EventKind.BASELINE_REPRODUCED))

        feedback: str | None = None
        seen: dict[str, int] = {}
        while True:
            if self._cancelled(run_id):
                return RunStatus.CANCELLED, "cancellation requested"
            exhausted = guard.exhausted_reason()
            if exhausted:
                return RunStatus.FAILED, exhausted

            number = guard.attempts_made + 1
            request = RepairRequest(task, number, feedback, guard.remaining())
            guard.record_attempt()
            self._emit(run_id, ProgressEvent(kind=EventKind.ATTEMPT_STARTED, attempt=number))
            outcome = self.repairer.propose(request)
            guard.record_usage(outcome.usage)
            self.store.set_estimated_cost(run_id, guard.estimated_cost_usd)

            candidate = outcome.candidate
            if candidate is None:
                feedback = outcome.rejection_reason
                self._record(run_id, number, None, "patch_invalid", feedback, None, outcome)
                continue

            patch_path = self.artifacts.write_patch(run_id, number, candidate.diff)
            if candidate.diff in seen:
                feedback = f"duplicate of attempt {seen[candidate.diff]}; propose a different fix"
                self._record(
                    run_id, number, candidate.method, "patch_invalid", feedback, patch_path, outcome
                )
                continue
            seen[candidate.diff] = number

            result = self.validator.validate(
                task, self.artifacts.evidence_dir(run_id, number), candidate
            )
            if result.report is not None:
                self.store.add_test_results(run_id, number, result.report.results)
            attempt_status = ATTEMPT_STATUS.get(result.status)
            if attempt_status is None:
                # Infrastructure problem (or an unexpected status): not the repair's fault.
                detail = summarize_failure(result.status, result.reason, result.report)
                self._record(run_id, number, candidate.method, "error", detail, patch_path, outcome)
                return RunStatus.ERROR, f"validation error on attempt {number}: {detail}"
            if attempt_status == "tests_passed":
                self._record(
                    run_id, number, candidate.method, attempt_status, None, patch_path, outcome
                )
                self.artifacts.write_final_patch(run_id, candidate.diff)
                return RunStatus.VERIFIED, f"verified by attempt {number}"
            feedback = summarize_failure(result.status, result.reason, result.report)
            self._record(
                run_id, number, candidate.method, attempt_status, feedback, patch_path, outcome
            )

    def _record(
        self,
        run_id: str,
        number: int,
        method: str | None,
        status: str,
        summary: str | None,
        patch_path: str | None,
        outcome: RepairOutcome,
    ) -> None:
        attempt = Attempt(
            run_id=run_id,
            number=number,
            method=method,
            status=status,
            patch_path=patch_path,
            error_summary=summary,
        )
        self.store.add_attempt(attempt, outcome.usage)
        data = {
            "status": status,
            "input_tokens": outcome.usage.input_tokens,
            "output_tokens": outcome.usage.output_tokens,
        }
        self._emit(
            run_id,
            ProgressEvent(
                kind=EventKind.ATTEMPT_FINISHED,
                attempt=number,
                message=summary or "",
                data=data,
            ),
        )

    def _cancelled(self, run_id: str) -> bool:
        return self.store.is_cancel_requested(run_id)

    def _emit(self, run_id: str, event: ProgressEvent) -> None:
        self.store.append_event(run_id, event)
