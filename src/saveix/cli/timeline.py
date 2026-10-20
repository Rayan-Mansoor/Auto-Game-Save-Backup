"""`saveix timeline` command."""

import typer

from saveix.cli.common import open_catalog
from saveix.cli.scan import human_size
from saveix.core.timeline import timeline as build_timeline


def timeline(
    game: str,
    limit: int = typer.Option(0, "--limit", "-n", help="Show only the newest N snapshots."),
) -> None:
    """List every snapshot of a game, newest first."""
    with open_catalog() as catalog:
        target = catalog.get_game(game)
        entries = build_timeline(catalog, target)
    if not entries:
        typer.echo(f"{target.name} has no snapshots yet; take one with `saveix backup`.")
        return
    if limit:
        entries = entries[:limit]
    for entry in entries:
        snap = entry.snapshot
        when = entry.local_time.strftime("%Y-%m-%d %H:%M")
        label = f'"{entry.label}"' if entry.custom_label else entry.label
        typer.echo(
            f"#{snap.id:<5} {when}  {label:<24} "
            f"{snap.file_count} files, {human_size(snap.total_size)}"
        )
        if snap.note:
            typer.echo(f"       note: {snap.note}")
