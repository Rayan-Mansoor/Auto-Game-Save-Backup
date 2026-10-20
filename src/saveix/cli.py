"""Command-line interface for saveix."""

import dataclasses

import typer

from saveix import __version__
from saveix.core.config import Config

app = typer.Typer(
    help="Automatic, versioned backups of local game save files.", no_args_is_help=True
)
config_app = typer.Typer(help="Show and change settings.", no_args_is_help=True)
app.add_typer(config_app, name="config")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"saveix {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Automatic, versioned backups of local game save files."""


@config_app.command("show")
def config_show() -> None:
    """Show all settings and where saveix stores its files."""
    config = Config()
    typer.echo(f"config file: {config.dirs.config_file}")
    typer.echo(f"data dir:    {config.dirs.data_dir}")
    typer.echo(f"backups:     {config.backup_root}")
    typer.echo("")
    for key, value in dataclasses.asdict(config.settings).items():
        if isinstance(value, list):
            value = ", ".join(value)
        typer.echo(f"{key} = {value}")


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Change a setting (lists are comma-separated)."""
    config = Config()
    try:
        config.settings.set(key, value)
    except KeyError:
        typer.echo(f"Unknown setting '{key}'. Known: {', '.join(config.settings.keys())}", err=True)
        raise typer.Exit(1) from None
    except ValueError as exc:
        typer.echo(f"Invalid value for {key}: {exc}", err=True)
        raise typer.Exit(1) from None
    config.save()
    typer.echo(f"{key} = {getattr(config.settings, key)}")
