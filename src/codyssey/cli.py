"""Starter CLI for inspecting the installation and validating task input."""

from pathlib import Path

import typer
from pydantic import ValidationError

from codyssey import __version__
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


if __name__ == "__main__":
    app()
