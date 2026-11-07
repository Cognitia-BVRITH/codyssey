"""Supplied-patch handoff shared by every future repair strategy."""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from codyssey.contracts import PatchCandidate, Task, TestReport
from codyssey.repository import checkout
from codyssey.sandbox.evidence import evidence_errors


class Executor(Protocol):
    def run(self, task: Task, repository: Path, artifacts: Path) -> TestReport:
        """Execute required tests in a disposable environment and return evidence."""
        ...


@dataclass(frozen=True)
class ValidationOutcome:
    status: Literal["reproduced", "verified", "patch_invalid", "tests_failed", "timeout", "error"]
    report: TestReport | None = None
    reason: str | None = None


def apply_candidate(repository: Path, candidate: PatchCandidate) -> None:
    """Check actual diff paths before applying; candidate metadata is not trusted."""
    patch = repository.parent / "candidate.diff"
    if any(
        line.startswith(
            (
                "old mode ",
                "new mode ",
                "new file mode ",
                "deleted file mode ",
                "rename from ",
                "rename to ",
            )
        )
        for line in candidate.diff.splitlines()
    ):
        raise ValueError("Mode changes, additions, deletions, and renames are unsupported")
    patch.write_text(candidate.diff, encoding="utf-8", newline="")
    summary = subprocess.run(
        ["git", "-C", str(repository), "apply", "--numstat", "-z", str(patch)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    paths = []
    for entry in summary.stdout.decode("utf-8").split("\0"):
        if not entry:
            continue
        added, removed, path = entry.split("\t", 2)
        parts = path.split("/")
        if (
            added == "-"
            or removed == "-"
            or not path
            or "\\" in path
            or ":" in path
            or path.startswith("/")
            or any(p in ("", ".", "..") for p in parts)
            or any(p.startswith(".") for p in parts)
            or any(
                p.lower()
                in {
                    "tests",
                    "test",
                    "conftest.py",
                    "pyproject.toml",
                    "pytest.ini",
                    "setup.cfg",
                    "tox.ini",
                }
                for p in parts
            )
            or Path(path).name.startswith("test_")
            or Path(path).stem.endswith("_test")
        ):
            raise ValueError(f"Candidate edits a protected or unsafe path: {path}")
        target = repository / path
        if not target.is_file() or any(p.is_symlink() for p in [target, *target.parents]):
            raise ValueError("Only existing regular source files may be patched")
        paths.append(path)
    if not paths or set(paths) != set(candidate.touched_paths):
        raise ValueError("Diff paths do not match touched_paths")
    subprocess.run(
        ["git", "-C", str(repository), "apply", "--check", str(patch)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    subprocess.run(
        ["git", "-C", str(repository), "apply", str(patch)],
        check=True,
        capture_output=True,
        timeout=30,
    )


class Validator:
    """Fresh checkout per call; baseline acceptance is an orchestrator precondition.

    Artifact directories must be new so prior evidence cannot be reused.
    This API does not mutate the original repository or persist run lifecycle.
    """

    def __init__(self, executor: Executor):
        self.executor = executor

    def validate(
        self,
        task: Task,
        artifacts: Path,
        candidate: PatchCandidate | None = None,
    ) -> ValidationOutcome:
        artifacts = artifacts.resolve()
        artifacts.mkdir(parents=True, exist_ok=False)
        try:
            with tempfile.TemporaryDirectory(prefix="codyssey-") as temporary:
                repository = checkout(task.repo_url, task.base_commit, Path(temporary) / "repo")
                if candidate is not None:
                    try:
                        apply_candidate(repository, candidate)
                    except (ValueError, subprocess.CalledProcessError) as exc:
                        return ValidationOutcome("patch_invalid", reason=str(exc))
                report = self.executor.run(task, repository, artifacts)
                errors = evidence_errors(task, report, baseline=candidate is None)
                if report.timed_out:
                    return ValidationOutcome("timeout", report, "; ".join(errors))
                if report.exit_code not in (0, 1):
                    return ValidationOutcome("error", report, "; ".join(errors))
                if errors:
                    status = "error" if candidate is None else "tests_failed"
                    return ValidationOutcome(status, report, "; ".join(errors))
                return ValidationOutcome("reproduced" if candidate is None else "verified", report)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return ValidationOutcome("error", reason=str(exc))
