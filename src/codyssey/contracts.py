"""Shared data contracts; execution and persistence are implemented separately."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    VERIFIED = "verified"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {RunStatus.VERIFIED, RunStatus.FAILED, RunStatus.ERROR, RunStatus.CANCELLED}
)

# `running -> error` also covers marking interrupted work after a worker restart.
ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: TERMINAL_STATUSES,
    RunStatus.VERIFIED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.ERROR: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


class Task(Contract):
    """A prepared repository task, independent of any repair strategy."""

    id: str = Field(min_length=1)
    repo_url: str = Field(min_length=1)
    base_commit: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    issue_title: str = Field(min_length=1)
    issue_body: str = Field(min_length=1)
    environment_image: str = Field(min_length=1)
    test_command: list[str] = Field(min_length=1)
    fail_to_pass: list[str] = Field(min_length=1)
    pass_to_pass: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_test_groups(self) -> "Task":
        for label, values in (
            ("test_command", self.test_command),
            ("fail_to_pass", self.fail_to_pass),
            ("pass_to_pass", self.pass_to_pass),
        ):
            if any(not value.strip() for value in values):
                raise ValueError(f"{label} cannot contain blank entries")
        for values in (self.fail_to_pass, self.pass_to_pass):
            if len(values) != len(set(values)):
                raise ValueError("Test groups cannot contain duplicate test identities")
        if set(self.fail_to_pass) & set(self.pass_to_pass):
            raise ValueError("Failing and regression test groups must be disjoint")
        return self


class PatchCandidate(Contract):
    """A proposed diff; validation of paths and applicability happens in the sandbox."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    diff: str = Field(min_length=1)
    method: Literal["deterministic", "llm"]
    touched_paths: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_touched_paths(self) -> "PatchCandidate":
        if any(not path.strip() for path in self.touched_paths):
            raise ValueError("touched_paths cannot contain blank entries")
        if len(self.touched_paths) != len(set(self.touched_paths)):
            raise ValueError("touched_paths cannot contain duplicates")
        return self


class RepairUsage(Contract):
    """Provider usage totals across every request made to produce one outcome."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    # Billable provider requests, including format retries and localization calls.
    requests: int = Field(default=0, ge=0)


class RepairOutcome(Contract):
    """Result of one repair request: a candidate, or an explicit reason for none."""

    candidate: PatchCandidate | None = None
    rejection_reason: str | None = Field(default=None, min_length=1)
    usage: RepairUsage = Field(default_factory=RepairUsage)

    @model_validator(mode="after")
    def validate_candidate_or_reason(self) -> "RepairOutcome":
        if (self.candidate is None) == (self.rejection_reason is None):
            raise ValueError("Provide exactly one of candidate or rejection_reason")
        return self


class TestResult(Contract):
    node_id: str = Field(min_length=1)
    group: Literal["fail_to_pass", "pass_to_pass"]
    outcome: Literal["passed", "failed", "error", "skipped"]
    duration_seconds: float = Field(default=0, ge=0)


class TestReport(Contract):
    """Evidence only; the validator must check completeness against the task."""

    results: list[TestResult] = Field(default_factory=list)
    exit_code: int
    timed_out: bool = False
    collection_errors: list[str] = Field(default_factory=list)
    output_path: str | None = None


class LLMResponse(Contract):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    text: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


class Attempt(Contract):
    run_id: str = Field(min_length=1)
    number: int = Field(ge=1)
    # None when the repair component returned no candidate to classify.
    method: Literal["deterministic", "llm"] | None = None
    status: Literal["patch_invalid", "tests_failed", "tests_passed", "timeout", "error"]
    patch_path: str | None = None
    error_summary: str | None = None


class Run(Contract):
    id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    status: RunStatus = RunStatus.QUEUED
    status_reason: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class EventKind(StrEnum):
    RUN_QUEUED = "run_queued"
    RUN_STARTED = "run_started"
    BASELINE_REPRODUCED = "baseline_reproduced"
    ATTEMPT_STARTED = "attempt_started"
    ATTEMPT_FINISHED = "attempt_finished"
    CANCEL_REQUESTED = "cancel_requested"
    RUN_FINISHED = "run_finished"


class ProgressEvent(Contract):
    """Payload shared by the CLI, API stream, and dashboard; storage adds ordering."""

    kind: EventKind
    attempt: int | None = Field(default=None, ge=1)
    message: str = ""
    data: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class StoredEvent(Contract):
    """A persisted event; `sequence` is per run and starts at 1 (usable as an SSE id)."""

    run_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    created_at: datetime
    event: ProgressEvent
