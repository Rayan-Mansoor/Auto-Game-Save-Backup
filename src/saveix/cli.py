"""Command-line interface for saveix."""

import typer

from saveix import __version__

app = typer.Typer(
    help="Automatic, versioned backups of local game save files.", no_args_is_help=True
)


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
