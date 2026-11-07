"""Starter CLI for inspecting the installation and validating task input."""

from pathlib import Path

import typer
from pydantic import ValidationError

from codyssey import __version__
from codyssey.config import ConfigError, load_config
from codyssey.contracts import Task

app = typer.Typer(help="Codyssey starter CLI. Automated repair is not implemented yet.")


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


if __name__ == "__main__":
    app()
