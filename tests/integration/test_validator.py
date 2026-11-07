"""Trusted local fixture execution only; production validation always uses Docker."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from codyssey.contracts import PatchCandidate, Task
from codyssey.repository import checkout
from codyssey.sandbox.docker import DockerExecutor
from codyssey.sandbox.evidence import read_junit
from codyssey.sandbox.validator import Validator


@pytest.fixture
def prepared(tmp_path):
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures" / "boundary", source)
    for args in (
        ["init"],
        ["add", "."],
        ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "fixture"],
    ):
        subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True)
    task = Task(
        id="boundary",
        repo_url=str(source),
        base_commit=commit.strip(),
        issue_title="Voting age",
        issue_body="18 must be eligible",
        environment_image=os.environ.get("CODYSSEY_TEST_IMAGE", "codyssey-fixture:local"),
        test_command=["python", "-m", "pytest"],
        fail_to_pass=["test_voting.py::test_at_voting_age"],
        pass_to_pass=[
            "test_voting.py::test_below_voting_age",
            "test_voting.py::test_above_voting_age",
        ],
    )
    return source, task


class TrustedFixtureExecutor:
    def run(self, task, repository, artifacts):
        path = artifacts / "junit.xml"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--import-mode=prepend",
                f"--junitxml={path}",
                *task.fail_to_pass,
                *task.pass_to_pass,
            ],
            cwd=repository,
            capture_output=True,
            timeout=30,
        )
        return read_junit(path, task, result.returncode)


def candidate():
    return PatchCandidate(
        diff="--- a/voting.py\n+++ b/voting.py\n@@ -5 +5 @@\n"
        "-    return age > 18\n+    return age >= 18\n",
        method="deterministic",
        touched_paths=["voting.py"],
    )


def exercise(validator, task, tmp_path):
    assert validator.validate(task, tmp_path / "baseline").status == "reproduced"
    outcome = validator.validate(task, tmp_path / "valid", candidate())
    assert outcome.status == "verified", outcome.reason
    # A fresh invocation must reproduce the original bug, even after a passing candidate.
    assert validator.validate(task, tmp_path / "reset").status == "reproduced"
    wrong = candidate()
    wrong.diff = wrong.diff.replace("age >= 18", "age > 19")
    assert validator.validate(task, tmp_path / "wrong", wrong).status == "tests_failed"


def test_supplied_patch_and_isolation(prepared, tmp_path):
    source, task = prepared
    exercise(Validator(TrustedFixtureExecutor()), task, tmp_path)
    assert "return age > 18" in (source / "voting.py").read_text()
    assert subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"]) == b""


@pytest.mark.parametrize("problem", ["metadata", "test_edit", "malformed", "mode", "traversal"])
def test_rejects_invalid_candidates(prepared, tmp_path, problem):
    _, task = prepared
    patch = candidate()
    if problem == "metadata":
        patch.touched_paths = ["other.py"]
    elif problem == "test_edit":
        patch.diff = patch.diff.replace("voting.py", "test_voting.py")
        patch.touched_paths = ["test_voting.py"]
    elif problem == "mode":
        patch.diff = "old mode 100644\nnew mode 100755\n" + patch.diff
    elif problem == "traversal":
        patch.diff = patch.diff.replace("voting.py", "../outside.py")
        patch.touched_paths = ["../outside.py"]
    else:
        patch.diff = "not a patch"
    assert (
        Validator(TrustedFixtureExecutor())
        .validate(
            task,
            tmp_path / problem,
            patch,
        )
        .status
        == "patch_invalid"
    )


def test_checkout_rejects_mutable_revision_and_existing_destination(prepared, tmp_path):
    source, task = prepared
    with pytest.raises(ValueError):
        checkout(str(source), "main", tmp_path / "target")
    with pytest.raises(FileExistsError):
        checkout(str(source), task.base_commit, source)


@pytest.mark.skipif(
    not os.environ.get("CODYSSEY_TEST_IMAGE"),
    reason="Set CODYSSEY_TEST_IMAGE to a prepared Docker image",
)
def test_docker_supplied_patch(prepared, tmp_path):
    _, task = prepared
    exercise(Validator(DockerExecutor()), task, tmp_path)
