"""`saveix config` commands."""

import dataclasses

import typer

from saveix.cli.common import fail
from saveix.core.config import Config

app = typer.Typer(help="Show and change settings.", no_args_is_help=True)


@app.command("show")
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


@app.command("set")
def config_set(key: str, value: str) -> None:
    """Change a setting (lists are comma-separated)."""
    config = Config()
    try:
        config.settings.set(key, value)
    except KeyError:
        fail(f"Unknown setting '{key}'. Known: {', '.join(config.settings.keys())}")
    except ValueError as exc:
        fail(f"Invalid value for {key}: {exc}")
    config.save()
    typer.echo(f"{key} = {getattr(config.settings, key)}")
