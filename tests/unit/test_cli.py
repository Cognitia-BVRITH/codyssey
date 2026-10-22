from typer.testing import CliRunner

from codyssey.cli import app

runner = CliRunner()


def test_invalid_task_returns_failure(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")
    result = runner.invoke(app, ["validate-task", str(path)])
    assert result.exit_code == 1
    assert "Invalid task" in result.output


def test_missing_task_returns_failure(tmp_path):
    result = runner.invoke(app, ["validate-task", str(tmp_path / "missing.json")])
    assert result.exit_code == 1


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
