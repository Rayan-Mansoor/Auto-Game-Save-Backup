"""`saveix backup` command."""

import typer

from saveix.cli.common import fail, open_catalog
from saveix.core.backup import BackupEngine, NothingToBackUpError
from saveix.core.config import Config
from saveix.core.context import context_for
from saveix.core.models import Trigger
from saveix.core.store import ObjectStore
from saveix.core.text import human_size


def backup(game: str) -> None:
    """Take a snapshot of a game's saves now."""
    config = Config()
    with open_catalog(config) as catalog:
        target = catalog.get_game(game)
        engine = BackupEngine(catalog, ObjectStore(config.backup_root))
        try:
            result = engine.backup(target, context_for(target), Trigger.MANUAL)
        except NothingToBackUpError as exc:
            fail(str(exc))

    for path, error in result.source_errors:
        typer.echo(f"warning: {path}: {error}", err=True)
    for path, reason in result.skipped:
        typer.echo(f"warning: skipped {path}: {reason}", err=True)
    if result.unchanged:
        typer.echo(f"No changes since snapshot #{result.previous.id}; nothing new saved.")
        return
    snap = result.snapshot
    typer.echo(
        f"Snapshot #{snap.id} of {target.name}: {snap.file_count} files, "
        f"{human_size(snap.total_size)} ({result.changed_files} new or changed)."
    )
