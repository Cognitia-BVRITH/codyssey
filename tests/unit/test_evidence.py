from pathlib import Path

import pytest

from codyssey.contracts import Task
from codyssey.contracts import TestReport as Report
from codyssey.contracts import TestResult as Result
from codyssey.sandbox.evidence import evidence_errors, read_junit


@pytest.fixture
def task():
    return Task(
        id="boundary",
        repo_url="local",
        base_commit="a" * 40,
        issue_title="Boundary",
        issue_body="Age 18 should pass",
        environment_image="fixture",
        test_command=["python", "-m", "pytest"],
        fail_to_pass=["test_voting.py::test_at_voting_age"],
        pass_to_pass=["test_voting.py::test_below_voting_age"],
    )


def report_for(task, baseline=False):
    return Report(
        exit_code=1 if baseline else 0,
        results=[
            Result(
                node_id=task.fail_to_pass[0],
                group="fail_to_pass",
                outcome="failed" if baseline else "passed",
            ),
            Result(node_id=task.pass_to_pass[0], group="pass_to_pass", outcome="passed"),
        ],
    )


@pytest.mark.parametrize("baseline", [True, False])
def test_complete_evidence(task, baseline):
    assert evidence_errors(task, report_for(task, baseline), baseline=baseline) == []


@pytest.mark.parametrize(
    "problem",
    ["missing", "duplicate", "skipped", "group", "timeout", "collection", "exit", "unexpected"],
)
def test_incomplete_or_invalid_evidence_never_verifies(task, problem):
    report = report_for(task)
    if problem == "missing":
        report.results.pop()
    elif problem == "duplicate":
        report.results.append(report.results[0])
    elif problem == "skipped":
        report.results[0].outcome = "skipped"
    elif problem == "group":
        report.results[0].group = "pass_to_pass"
    elif problem == "timeout":
        report.timed_out = True
    elif problem == "collection":
        report.collection_errors.append("collection failed")
    elif problem == "exit":
        report.exit_code = 2
    else:
        report.results[0].node_id = "unknown"
    assert evidence_errors(task, report)


def test_baseline_must_reproduce_failure(task):
    report = report_for(task)
    report.exit_code = 1
    assert evidence_errors(task, report, baseline=True)


def test_missing_and_malformed_junit(task, tmp_path: Path):
    path = tmp_path / "junit.xml"
    assert read_junit(path, task, 0).collection_errors
    path.write_text("not XML")
    assert read_junit(path, task, 0).collection_errors


def test_junit_preserves_parameter_identity(task, tmp_path):
    task.fail_to_pass = ["tests/test_voting.py::TestVoting::test_age[a.b]"]
    path = tmp_path / "junit.xml"
    path.write_text(
        '<testsuites><testsuite><testcase classname="tests.test_voting.TestVoting" '
        'name="test_age[a.b]" time="0.1"><failure/></testcase>'
        "</testsuite></testsuites>"
    )
    report = read_junit(path, task, 1)
    assert report.results[0].node_id == task.fail_to_pass[0]
    assert report.results[0].outcome == "failed"
