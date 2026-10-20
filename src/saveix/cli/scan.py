"""`saveix scan` command."""

import typer

from saveix.cli.common import open_catalog
from saveix.core.paths import PathContext
from saveix.core.sources.resolve import scan_game


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError


def scan(
    game: str, files: bool = typer.Option(False, "--files", "-f", help="List every file.")
) -> None:
    """Show which files a game's sources currently cover."""
    with open_catalog() as catalog:
        target = catalog.get_game(game)
    scans = scan_game(target, PathContext.for_system())
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
