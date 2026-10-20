"""`saveix timeline` command."""

import typer

from saveix.cli.common import open_catalog
from saveix.cli.scan import human_size
from saveix.core.timeline import timeline as build_timeline

HEALTH_MARKS = {"ok": "✓", "suspicious": "⚠", None: " "}


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
            f"{HEALTH_MARKS.get(snap.health, ' ')} #{snap.id:<5} {when}  {label:<24} "
            f"{snap.file_count} files, {human_size(snap.total_size)}"
        )
        for problem in snap.health_notes:
            typer.echo(f"         ⚠ {problem}")
        if snap.note:
            typer.echo(f"         note: {snap.note}")


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


def check(snapshot_id: int) -> None:
    """Run the health checks on a snapshot again and show the result."""
    from saveix.core.backup import BackupEngine
    from saveix.core.config import Config
    from saveix.core.models import Trigger
    from saveix.core.store import ObjectStore

    config = Config()
    with open_catalog(config) as catalog:
        snap = catalog.get_snapshot(snapshot_id)
        crashed = (
            snap.trigger is Trigger.SESSION_END
            and snap.session_id is not None
            and catalog.get_session(snap.session_id).crashed
        )
        engine = BackupEngine(catalog, ObjectStore(config.backup_root))
        snap = engine.check(snap, crashed=crashed)
    if snap.health == "ok":
        typer.echo(f"✓ Snapshot #{snap.id} looks healthy.")
        return
    typer.echo(f"⚠ Snapshot #{snap.id} looks damaged:")
    for problem in snap.health_notes:
        typer.echo(f"  {problem}")
