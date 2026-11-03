"""Shared data contracts; execution and persistence are implemented separately."""

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
    method: Literal["deterministic", "llm"]
    status: Literal["patch_invalid", "tests_failed", "tests_passed", "timeout", "error"]
    patch_path: str | None = None
    error_summary: str | None = None


class Run(Contract):
    id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    status: RunStatus = RunStatus.QUEUED
