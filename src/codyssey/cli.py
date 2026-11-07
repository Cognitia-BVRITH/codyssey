"""Starter CLI for inspecting the installation and validating task input."""

from pathlib import Path

import typer
from pydantic import ValidationError

from codyssey import __version__
from codyssey.config import CodysseyConfig, ConfigError, load_config
from codyssey.contracts import Task
from codyssey.storage import RunNotFound, RunStore

app = typer.Typer(help="Codyssey starter CLI. Automated repair is not implemented yet.")
runs_app = typer.Typer(help="Inspect recorded runs.")
app.add_typer(runs_app, name="runs")

ConfigOption = typer.Option(
    None, "--config", help="Configuration file; defaults locate the database under data/."
)


def _open_existing_store(config_path: Path | None) -> RunStore | None:
    """Open the configured database for reading; None when nothing has been recorded."""
    try:
        config = load_config(config_path) if config_path else CodysseyConfig()
    except ConfigError as exc:
        typer.echo(f"Invalid config: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not config.storage.database_path.is_file():
        return None
    return RunStore(config.storage.database_path)


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(__version__)


@app.command()
def validate_task(path: Path) -> None:
    """Validate a prepared task JSON file without executing repository code."""
    try:
        task = Task.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        typer.echo(f"Invalid task: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Valid task: {task.id}")


@app.command()
def validate_config(path: Path) -> None:
    """Validate a runtime configuration file without contacting any service."""
    try:
        config = load_config(path)
    except ConfigError as exc:
        typer.echo(f"Invalid config: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Valid config: strategy={config.repair.strategy}")


@runs_app.command("list")
def runs_list(
    limit: int = typer.Option(20, min=1, help="Maximum runs to show."),
    config: Path | None = ConfigOption,
) -> None:
    """List recent runs, newest first."""
    store = _open_existing_store(config)
    runs = store.list_runs(limit) if store else []
    if not runs:
        typer.echo("No runs recorded.")
        return
    for run in runs:
        created = run.created_at.isoformat(timespec="seconds") if run.created_at else "-"
        typer.echo(f"{run.id}  {run.status.value:<9}  {run.task_id}  {created}")


@runs_app.command("show")
def runs_show(run_id: str, config: Path | None = ConfigOption) -> None:
    """Show one run with its attempts and usage."""
    store = _open_existing_store(config)
    try:
        if store is None:
            raise RunNotFound(run_id)
        run = store.get_run(run_id)
    except RunNotFound as exc:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Run {run.id}  [{run.status.value}]  task={run.task_id}")
    if run.status_reason:
        typer.echo(f"Reason: {run.status_reason}")
    usage = store.total_usage(run_id)
    cost = store.get_estimated_cost(run_id)
    cost_text = "unknown" if cost is None else f"${cost:.4f} (estimated)"
    typer.echo(
        f"Usage: {usage.input_tokens} in / {usage.output_tokens} out tokens, "
        f"{usage.requests} requests, cost {cost_text}"
    )
    attempts = store.list_attempts(run_id)
    if not attempts:
        typer.echo("No attempts recorded.")
    for stored in attempts:
        attempt = stored.attempt
        line = f"  #{attempt.number} {attempt.status} ({attempt.method or 'no candidate'})"
        if attempt.error_summary:
            line += f" - {attempt.error_summary}"
        typer.echo(line)


if __name__ == "__main__":
    app()
