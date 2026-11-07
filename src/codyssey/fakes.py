"""Scripted stand-ins so components can be built and tested against the orchestrator.

`FakeValidator` mimics `sandbox.validator.Validator` (including its requirement that the
evidence directory is new) and `FakeRepairer` mimics a repair component. Neither touches
Docker, Git, or a provider.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from codyssey.contracts import (
    PatchCandidate,
    RepairOutcome,
    Task,
    TestReport,
    TestResult,
)
from codyssey.orchestrator import RepairRequest


@dataclass(frozen=True)
class FakeValidation:
    status: str
    report: TestReport | None = None
    reason: str | None = None


def make_report(task: Task, *, fixed: bool, exit_code: int | None = None) -> TestReport:
    """Complete report for a task: the failing group passes only when `fixed`."""
    results = [
        TestResult(
            node_id=node,
            group="fail_to_pass",
            outcome="passed" if fixed else "failed",
        )
        for node in task.fail_to_pass
    ] + [
        TestResult(node_id=node, group="pass_to_pass", outcome="passed")
        for node in task.pass_to_pass
    ]
    code = exit_code if exit_code is not None else (0 if fixed else 1)
    return TestReport(results=results, exit_code=code)


def baseline_reproduced(task: Task) -> FakeValidation:
    return FakeValidation("reproduced", make_report(task, fixed=False))


def attempt_verified(task: Task) -> FakeValidation:
    return FakeValidation("verified", make_report(task, fixed=True))


def attempt_failed(task: Task, reason: str = "required tests did not pass") -> FakeValidation:
    return FakeValidation("tests_failed", make_report(task, fixed=False), reason)


class FakeValidator:
    """Returns the baseline result for candidate-less calls, then scripted attempt results."""

    def __init__(self, baseline: FakeValidation, attempts: Iterable[FakeValidation] = ()):
        self.baseline = baseline
        self._attempts = iter(attempts)
        self.calls: list[tuple[Path, PatchCandidate | None]] = []

    def validate(
        self, task: Task, artifacts: Path, candidate: PatchCandidate | None = None
    ) -> FakeValidation:
        artifacts.mkdir(parents=True, exist_ok=False)
        self.calls.append((artifacts, candidate))
        if candidate is None:
            return self.baseline
        try:
            return next(self._attempts)
        except StopIteration:
            raise AssertionError("FakeValidator has no scripted result left") from None


class FakeRepairer:
    """Returns scripted outcomes in order and records every request it receives."""

    def __init__(self, outcomes: Iterable[RepairOutcome]):
        self._outcomes = iter(outcomes)
        self.requests: list[RepairRequest] = []

    def propose(self, request: RepairRequest) -> RepairOutcome:
        self.requests.append(request)
        try:
            return next(self._outcomes)
        except StopIteration:
            raise AssertionError("FakeRepairer has no scripted outcome left") from None
