from pathlib import Path

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


def test_example_config_is_valid(tmp_path):
    example = Path(__file__).resolve().parents[2] / "config.example.yaml"
    result = runner.invoke(app, ["validate-config", str(example)])
    assert result.exit_code == 0
    assert "Valid config" in result.output


def test_invalid_config_returns_failure(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("repair: {max_attempts: 0}", encoding="utf-8")
    result = runner.invoke(app, ["validate-config", str(path)])
    assert result.exit_code == 1
    assert "Invalid config" in result.output
