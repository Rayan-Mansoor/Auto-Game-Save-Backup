"""Command-line interface for saveix."""

import sys

import typer

from saveix import __version__
from saveix.cli import (
    autostart,
    backup,
    config_cmd,
    detect,
    diff,
    emulators,
    games,
    identify,
    providers,
    prune,
    restore,
    run,
    scan,
    timeline,
)

app = typer.Typer(
    help="Automatic, versioned backups of local game save files.", no_args_is_help=True
)
app.add_typer(config_cmd.app, name="config")
app.add_typer(games.game_app, name="game")
app.add_typer(games.source_app, name="source")
app.add_typer(providers.app, name="providers")
app.command()(scan.scan)
app.command()(backup.backup)
app.command()(timeline.timeline)
app.command()(timeline.label)
app.command()(timeline.note)
app.command()(timeline.check)
app.command()(timeline.pin)
app.command()(timeline.unpin)
app.command()(diff.diff)
app.command()(restore.restore)
app.command()(identify.identify)
app.command()(emulators.emulators)
app.command()(run.run)
app.command()(run.tray)
app.command()(autostart.autostart)
app.command()(prune.prune)
app.command()(detect.detect)
app.command()(providers.search)
app.command()(providers.suggest)


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
    _safe_output()


def _safe_output() -> None:
    """Never crash on characters the output can't show.

    On Windows, output that is not a console window (a file, a pipe, Git Bash) uses the
    ANSI code page, which has no ✓ or ⚠; those are replaced instead of raising.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
