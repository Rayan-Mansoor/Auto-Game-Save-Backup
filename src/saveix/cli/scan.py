"""`saveix scan` command."""

import typer

from saveix.cli.common import open_catalog
from saveix.core.context import context_for
from saveix.core.sources.resolve import scan_game
from saveix.core.text import human_size


def scan(
    game: str, files: bool = typer.Option(False, "--files", "-f", help="List every file.")
) -> None:
    """Show which files a game's sources currently cover."""
    with open_catalog() as catalog:
        target = catalog.get_game(game)
    scans = scan_game(target, context_for(target))
    for result in scans:
        s = result.source
        if result.error:
            status = f"error: {result.error}"
        elif not result.files:
            status = "nothing found"
        else:
            status = f"{len(result.files)} files, {human_size(result.size)}"
        typer.echo(f"[{s.id}] {s.path}: {status}")
        if files:
            for f in result.files:
                typer.echo(f"      {f.template}  ({human_size(f.size)})")
    total_files = sum(len(r.files) for r in scans)
    total_size = sum(r.size for r in scans)
    typer.echo(f"Total: {total_files} files, {human_size(total_size)}")
