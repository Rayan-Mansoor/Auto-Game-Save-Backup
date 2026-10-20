"""`saveix diff` command."""

import typer

from saveix.cli.common import fail, open_catalog
from saveix.core.diff import Change, FileChange, diff_files
from saveix.core.text import human_size

SYMBOLS = {Change.ADDED: "+", Change.REMOVED: "-", Change.MODIFIED: "~"}


def describe(change: FileChange) -> str:
    line = f"  {SYMBOLS[change.change]} {change.template}"
    if change.change is Change.MODIFIED:
        line += f"  ({human_size(change.old_size)} -> {human_size(change.new_size)})"
    elif change.change is Change.ADDED:
        line += f"  ({human_size(change.new_size)})"
    return line


def diff(
    old: int = typer.Argument(..., help="Snapshot to compare from."),
    new: int | None = typer.Argument(
        None, help="Snapshot to compare to; defaults to the next one."
    ),
) -> None:
    """Show which files changed between two snapshots of a game."""
    with open_catalog() as catalog:
        first = catalog.get_snapshot(old)
        if new is None:
            second, first = first, catalog.previous_snapshot(first)
            if first is None:
                fail(f"Snapshot #{old} is the game's first snapshot; give two snapshot numbers.")
        else:
            second = catalog.get_snapshot(new)
        if first.game_id != second.game_id:
            fail("Those snapshots belong to different games.")
        changes = diff_files(catalog.snapshot_files(first.id), catalog.snapshot_files(second.id))
    typer.echo(f"#{first.id} -> #{second.id}:")
    if not changes:
        typer.echo("  no differences")
    for change in changes:
        typer.echo(describe(change))
