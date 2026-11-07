from typer.testing import CliRunner

from codyssey.cli import app
from codyssey.config import CodysseyConfig
from codyssey.contracts import Attempt, RepairUsage, RunStatus, Task
from codyssey.storage import RunStore

runner = CliRunner()


def make_config(tmp_path):
    database = tmp_path / "data" / "codyssey.db"
    path = tmp_path / "config.yaml"
    path.write_text(f"storage:\n  database_url: sqlite:///{database}\n", encoding="utf-8")
    return path, database


def make_task(task_id="t1"):
    return Task(
        id=task_id,
        repo_url="https://example.com/x.git",
        base_commit="b" * 40,
        issue_title="title",
        issue_body="body",
        environment_image="img",
        test_command=["pytest"],
        fail_to_pass=["a.py::f"],
        pass_to_pass=["a.py::p"],
    )


def test_list_without_a_database_reports_no_runs_and_creates_nothing(tmp_path):
    path, database = make_config(tmp_path)
    result = runner.invoke(app, ["runs", "list", "--config", str(path)])
    assert result.exit_code == 0
    assert "No runs recorded." in result.output
    assert not database.exists()


def test_list_and_show_recorded_runs(tmp_path):
    path, database = make_config(tmp_path)
    store = RunStore(database)
    store.add_task(make_task())
    store.create_run("t1", CodysseyConfig(), run_id="r1")
    store.create_run("t1", CodysseyConfig(), run_id="r2")
    store.transition("r1", RunStatus.RUNNING)
    store.add_attempt(
        Attempt(run_id="r1", number=1, method="llm", status="tests_failed", error_summary="boom"),
        RepairUsage(input_tokens=12, output_tokens=3, requests=1),
    )
    store.add_attempt(Attempt(run_id="r1", number=2, status="patch_invalid"))
    store.transition("r1", RunStatus.FAILED, "attempt limit reached (2)")

    listing = runner.invoke(app, ["runs", "list", "--config", str(path)])
    assert listing.exit_code == 0
    lines = listing.output.strip().splitlines()
    assert lines[0].startswith("r2") and lines[1].startswith("r1")
    assert "failed" in lines[1] and "queued" in lines[0]

    shown = runner.invoke(app, ["runs", "show", "r1", "--config", str(path)])
    assert shown.exit_code == 0
    assert "Run r1  [failed]  task=t1" in shown.output
    assert "Reason: attempt limit reached (2)" in shown.output
    assert "12 in / 3 out tokens, 1 requests, cost unknown" in shown.output
    assert "#1 tests_failed (llm) - boom" in shown.output
    assert "#2 patch_invalid (no candidate)" in shown.output


def test_show_unknown_run_fails(tmp_path):
    path, database = make_config(tmp_path)
    RunStore(database)
    result = runner.invoke(app, ["runs", "show", "nope", "--config", str(path)])
    assert result.exit_code == 1
    assert "Run not found: nope" in result.output


def test_show_without_a_database_fails_cleanly(tmp_path):
    path, _ = make_config(tmp_path)
    result = runner.invoke(app, ["runs", "show", "r1", "--config", str(path)])
    assert result.exit_code == 1


def test_runs_commands_reject_an_invalid_config(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("repair: {max_attempts: 0}", encoding="utf-8")
    result = runner.invoke(app, ["runs", "list", "--config", str(bad)])
    assert result.exit_code == 1
    assert "Invalid config" in result.output
