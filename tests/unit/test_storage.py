from datetime import UTC, datetime

import pytest

from codyssey import contracts
from codyssey.config import CodysseyConfig
from codyssey.contracts import (
    Attempt,
    EventKind,
    ProgressEvent,
    RepairUsage,
    RunStatus,
    Task,
)
from codyssey.storage import (
    ArtifactStore,
    InvalidTransition,
    RunNotFound,
    RunStore,
    StorageError,
    TaskConflict,
    TaskNotFound,
    new_run_id,
)


@pytest.fixture
def task():
    return Task(
        id="boundary-example",
        repo_url="https://example.com/team/fixture.git",
        base_commit="a" * 40,
        issue_title="Voting age boundary",
        issue_body="An eighteen-year-old must be eligible.",
        environment_image="codyssey-fixture:local",
        test_command=["python", "-m", "pytest"],
        fail_to_pass=["test_voting.py::test_at_voting_age"],
        pass_to_pass=["test_voting.py::test_below_voting_age"],
    )


@pytest.fixture
def store(tmp_path, task):
    ticks = iter(range(1, 10_000))
    clock = lambda: datetime(2026, 1, 1, tzinfo=UTC).replace(second=next(ticks) % 60)  # noqa: E731
    result = RunStore(tmp_path / "db" / "codyssey.db", clock=clock)
    result.add_task(task)
    return result


@pytest.fixture
def run(store, task):
    return store.create_run(task.id, CodysseyConfig(), run_id="r1")


def test_new_run_ids_are_unique_and_artifact_safe(tmp_path):
    first, second = new_run_id(), new_run_id()
    assert first != second
    ArtifactStore(tmp_path).run_dir(first)


def test_task_round_trips_and_is_idempotent(store, task):
    store.add_task(task)
    assert store.get_task(task.id) == task


def test_task_id_reuse_with_different_content_is_rejected(store, task):
    with pytest.raises(TaskConflict):
        store.add_task(task.model_copy(update={"issue_title": "Changed"}))


def test_missing_task_and_run_raise(store):
    with pytest.raises(TaskNotFound):
        store.get_task("nope")
    with pytest.raises(TaskNotFound):
        store.create_run("nope", CodysseyConfig())
    with pytest.raises(RunNotFound):
        store.get_run("nope")


def test_created_run_is_queued_with_event_and_config(store, run):
    assert run.status == RunStatus.QUEUED
    assert run.created_at is not None and run.started_at is None
    assert store.get_run_config("r1") == CodysseyConfig()
    assert [e.event.kind for e in store.list_events("r1")] == [EventKind.RUN_QUEUED]


def test_duplicate_run_id_is_rejected(store, task, run):
    with pytest.raises(StorageError):
        store.create_run(task.id, CodysseyConfig(), run_id="r1")


def test_forward_transitions_record_timestamps_and_reason(store, run):
    running = store.transition("r1", RunStatus.RUNNING)
    assert running.started_at is not None and running.finished_at is None
    done = store.transition("r1", RunStatus.FAILED, "attempt limit reached (5)")
    assert done.status == RunStatus.FAILED
    assert done.status_reason == "attempt limit reached (5)"
    assert done.finished_at is not None


@pytest.mark.parametrize("target", [RunStatus.VERIFIED, RunStatus.FAILED, RunStatus.ERROR])
def test_queued_run_cannot_skip_running(store, run, target):
    with pytest.raises(InvalidTransition):
        store.transition("r1", target)


def test_terminal_runs_never_change(store, run):
    store.transition("r1", RunStatus.RUNNING)
    store.transition("r1", RunStatus.VERIFIED)
    for target in RunStatus:
        with pytest.raises(InvalidTransition):
            store.transition("r1", target)


def test_list_runs_is_newest_first(store, task, run):
    store.create_run(task.id, CodysseyConfig(), run_id="r2")
    assert [r.id for r in store.list_runs()] == ["r2", "r1"]
    assert [r.id for r in store.list_runs(limit=1)] == ["r2"]


def test_cancel_queued_run_is_immediate(store, run):
    cancelled = store.request_cancel("r1")
    assert cancelled.status == RunStatus.CANCELLED
    kinds = [e.event.kind for e in store.list_events("r1")]
    assert kinds == [EventKind.RUN_QUEUED, EventKind.CANCEL_REQUESTED, EventKind.RUN_FINISHED]


def test_cancel_running_run_only_records_the_request(store, run):
    store.transition("r1", RunStatus.RUNNING)
    assert store.is_cancel_requested("r1") is False
    still_running = store.request_cancel("r1")
    assert still_running.status == RunStatus.RUNNING
    assert store.is_cancel_requested("r1") is True


def test_cancel_after_finish_changes_nothing(store, run):
    store.transition("r1", RunStatus.RUNNING)
    store.transition("r1", RunStatus.VERIFIED)
    assert store.request_cancel("r1").status == RunStatus.VERIFIED
    assert store.is_cancel_requested("r1") is False


def test_interrupted_runs_become_errors(store, task, run):
    store.transition("r1", RunStatus.RUNNING)
    store.create_run(task.id, CodysseyConfig(), run_id="r2")
    assert store.mark_interrupted_runs() == ["r1"]
    assert store.get_run("r1").status == RunStatus.ERROR
    assert "interrupted" in store.get_run("r1").status_reason
    assert store.get_run("r2").status == RunStatus.QUEUED


def test_events_are_ordered_and_resumable(store, run):
    store.append_event("r1", ProgressEvent(kind=EventKind.RUN_STARTED))
    stored = store.append_event(
        "r1", ProgressEvent(kind=EventKind.ATTEMPT_STARTED, attempt=1, data={"tokens": 3})
    )
    assert stored.sequence == 3
    after = store.list_events("r1", after=2)
    assert [e.sequence for e in after] == [3]
    assert after[0].event.data == {"tokens": 3}
    with pytest.raises(RunNotFound):
        store.append_event("missing", ProgressEvent(kind=EventKind.RUN_STARTED))


def test_attempts_usage_and_test_results(store, run):
    usage = RepairUsage(input_tokens=100, output_tokens=20, latency_ms=300, requests=2)
    store.add_attempt(
        Attempt(run_id="r1", number=1, method="llm", status="tests_failed", patch_path="r1/a"),
        usage,
    )
    store.add_attempt(
        Attempt(run_id="r1", number=2, status="patch_invalid", error_summary="no candidate"),
        RepairUsage(input_tokens=5, requests=1),
    )
    stored = store.list_attempts("r1")
    assert [s.attempt.number for s in stored] == [1, 2]
    assert stored[0].usage == usage
    assert stored[1].attempt.method is None
    total = store.total_usage("r1")
    assert (total.input_tokens, total.output_tokens, total.requests) == (105, 20, 3)
    with pytest.raises(StorageError):
        store.add_attempt(Attempt(run_id="r1", number=1, status="error"))
    results = [
        contracts.TestResult(
            node_id="t::a", group="fail_to_pass", outcome="passed", duration_seconds=0.5
        ),
        contracts.TestResult(node_id="t::b", group="pass_to_pass", outcome="failed"),
    ]
    store.add_test_results("r1", 0, results)
    assert store.list_test_results("r1", 0) == results
    assert store.list_test_results("r1", 1) == []


def test_estimated_cost_round_trips(store, run):
    assert store.get_estimated_cost("r1") is None
    store.set_estimated_cost("r1", 0.25)
    assert store.get_estimated_cost("r1") == 0.25


def test_state_survives_reopening_the_database(store, run):
    store.transition("r1", RunStatus.RUNNING)
    reopened = RunStore(store.database_path)
    assert reopened.get_run("r1").status == RunStatus.RUNNING


def test_artifacts_are_write_once(tmp_path):
    artifacts = ArtifactStore(tmp_path / "runs")
    relative = artifacts.write_patch("r1", 1, "--- a\n+++ b\n")
    assert relative == "r1/attempt1/patch.diff"
    assert artifacts.read_text(relative) == "--- a\n+++ b\n"
    with pytest.raises(FileExistsError):
        artifacts.write_patch("r1", 1, "other")


def test_artifact_diff_whitespace_is_preserved(tmp_path):
    artifacts = ArtifactStore(tmp_path)
    relative = artifacts.write_patch("r1", 1, "line\r\n  indented\n")
    assert (tmp_path / relative).read_bytes() == b"line\r\n  indented\n"


@pytest.mark.parametrize("bad", ["../x", "/abs", "a/../../x", "a\\b", ""])
def test_artifact_paths_cannot_escape_the_run(tmp_path, bad):
    with pytest.raises(ValueError):
        ArtifactStore(tmp_path).write_text("r1", bad, "x")


@pytest.mark.parametrize("bad", ["", "..", "a/b", ".hidden", "x" * 80, "a..b"])
def test_unsafe_run_ids_are_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        ArtifactStore(tmp_path).run_dir(bad)


def test_read_rejects_paths_outside_root(tmp_path):
    (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        ArtifactStore(tmp_path / "runs").read_text("../secret.txt")


def test_final_patch_is_absent_until_written(tmp_path):
    artifacts = ArtifactStore(tmp_path)
    assert artifacts.final_patch_path("r1") is None
    artifacts.write_final_patch("r1", "diff")
    assert artifacts.final_patch_path("r1") is not None


def test_validator_directories_are_not_pre_created(tmp_path):
    artifacts = ArtifactStore(tmp_path)
    artifacts.write_patch("r1", 1, "diff")
    assert not artifacts.evidence_dir("r1", 1).exists()
    assert not artifacts.baseline_dir("r1").exists()
