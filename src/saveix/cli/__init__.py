"""Command-line interface for saveix."""

import typer

from saveix import __version__
from saveix.cli import backup, config_cmd, games, scan, timeline

app = typer.Typer(
    help="Automatic, versioned backups of local game save files.", no_args_is_help=True
)
app.add_typer(config_cmd.app, name="config")
app.add_typer(games.game_app, name="game")
app.add_typer(games.source_app, name="source")
app.command()(scan.scan)
app.command()(backup.backup)
app.command()(timeline.timeline)
app.command()(timeline.label)
app.command()(timeline.note)


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
