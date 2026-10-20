"""`saveix restore` command."""

import typer

from saveix.cli.common import fail, open_catalog
from saveix.core.backup import BackupEngine
from saveix.core.config import Config
from saveix.core.context import context_for
from saveix.core.restore import Action, Restorer, cloud_warning
from saveix.core.sessions import running_games
from saveix.core.store import CorruptObjectError, ObjectStore


def restore(
    game: str,
    snapshot: int | None = typer.Option(
        None, "--snapshot", "-s", help="Snapshot to restore; defaults to the latest."
    ),
    source: list[int] = typer.Option(
        [], "--source", "-S", help="Only restore this source (see `game show`); repeatable."
    ),
    keep_extra: bool = typer.Option(
        False, help="Keep save files that did not exist in that snapshot."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only show what would change."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask to confirm."),
) -> None:
    """Put a game's saves back to any snapshot. The current state is saved first."""
    config = Config()
    with open_catalog(config) as catalog:
        target = catalog.get_game(game)
        context = context_for(target)
        if snapshot is None:
            chosen = catalog.latest_snapshot(target)
            if chosen is None:
                fail(f"{target.name} has no snapshots to restore.")
        else:
            chosen = catalog.get_snapshot(snapshot)
        store = ObjectStore(config.backup_root)
        restorer = Restorer(catalog, store, BackupEngine(catalog, store))
        plan = restorer.plan(
            target, chosen, context, remove_extra=not keep_extra, only_sources=set(source)
        )

        if not plan.has_changes:
            typer.echo(f"{target.name}'s saves already match snapshot #{chosen.id}.")
            return
        typer.echo(f"Restoring {target.name} to snapshot #{chosen.id} ({chosen.created_at}):")
        for item in plan.of(Action.WRITE):
            typer.echo(f"  write  {item.template}")
        for item in plan.of(Action.DELETE):
            typer.echo(f"  delete {item.template}")
        if dry_run:
            return
        if running_games([target]):
            fail(f"{target.name} is running; close it before restoring its saves.")
        warning = cloud_warning(target)
        if warning:
            typer.echo(f"warning: {warning}", err=True)
        if not yes:
            typer.confirm("Continue? Your current saves are backed up first.", abort=True)
        try:
            result = restorer.execute(plan, context)
        except CorruptObjectError as exc:
            fail(str(exc))

    if result.safety_snapshot:
        typer.echo(f"Current saves kept as snapshot #{result.safety_snapshot.id}.")
    typer.echo(f"Restored {result.written} files, removed {result.deleted}.")
