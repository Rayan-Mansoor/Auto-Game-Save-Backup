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


def label(
    snapshot_id: int,
    text: str = typer.Argument("", help="New label; leave out to go back to the automatic one."),
) -> None:
    """Name a snapshot, for example to mark a game stage."""
    with open_catalog() as catalog:
        snap = catalog.set_label(snapshot_id, text)
    if snap.label:
        typer.echo(f'Snapshot #{snap.id} is now labeled "{snap.label}".')
    else:
        typer.echo(f"Snapshot #{snap.id} uses its automatic label again.")


def note(
    snapshot_id: int,
    text: str = typer.Argument("", help="Note text; leave out to remove the note."),
) -> None:
    """Attach a note to a snapshot."""
    with open_catalog() as catalog:
        snap = catalog.set_note(snapshot_id, text)
    typer.echo(
        f"Saved note on snapshot #{snap.id}." if snap.note else f"Removed note from #{snap.id}."
    )
