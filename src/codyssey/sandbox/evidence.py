"""Interpret pytest JUnit evidence against the exact required test set."""

from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from codyssey.contracts import Task, TestReport, TestResult


def read_junit(path: Path, task: Task, exit_code: int, timed_out: bool = False) -> TestReport:
    """Match pytest's classname/name pair to required node IDs, rejecting ambiguity."""
    report = TestReport(exit_code=exit_code, timed_out=timed_out)
    identities: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for group in ("fail_to_pass", "pass_to_pass"):
        for node_id in getattr(task, group):
            parts = node_id.split("::")
            classname = parts[0].removesuffix(".py").replace("/", ".")
            key = (".".join([classname, *parts[1:-1]]), parts[-1])
            identities.setdefault(key, []).append((node_id, group))
    try:
        root = ElementTree.parse(path).getroot()
        for case in root.iter("testcase"):
            matches = identities.get((case.get("classname", ""), case.get("name", "")), [])
            if len(matches) != 1:
                report.collection_errors.append("Unexpected or ambiguous JUnit test identity")
                continue
            node_id, group = matches[0]
            outcome = "passed"
            for tag, value in (("skipped", "skipped"), ("failure", "failed"), ("error", "error")):
                if case.find(tag) is not None:
                    outcome = value
            report.results.append(
                TestResult(
                    node_id=node_id,
                    group=group,
                    outcome=outcome,
                    duration_seconds=float(case.get("time", "0")),
                )
            )
    except (OSError, ElementTree.ParseError, ValueError) as exc:
        report.collection_errors.append(f"Invalid JUnit report: {exc}")
    return report


def evidence_errors(task: Task, report: TestReport, *, baseline: bool = False) -> list[str]:
    """A zero exit status alone never establishes reproduction or verification."""
    errors = list(report.collection_errors)
    if report.timed_out:
        errors.append("Test execution timed out")
    expected_exit = 1 if baseline else 0
    if report.exit_code != expected_exit:
        errors.append(f"Expected pytest exit {expected_exit}, got {report.exit_code}")
    required = {
        **{node: "fail_to_pass" for node in task.fail_to_pass},
        **{node: "pass_to_pass" for node in task.pass_to_pass},
    }
    counts = Counter(result.node_id for result in report.results)
    for node in required:
        if counts[node] != 1:
            errors.append(f"Required test must appear exactly once: {node}")
    for result in report.results:
        if required.get(result.node_id) != result.group:
            errors.append(f"Unexpected test or group: {result.node_id}")
        expected = "failed" if baseline and result.group == "fail_to_pass" else "passed"
        if result.outcome != expected:
            errors.append(f"Expected {expected}: {result.node_id} ({result.outcome})")
    return errors
