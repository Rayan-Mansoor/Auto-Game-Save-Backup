"""`saveix prune` command and the retention hook used by the runner."""

from datetime import UTC, datetime

import typer

from saveix.cli.common import open_catalog
from saveix.core.catalog import Catalog
from saveix.core.config import Config
from saveix.core.models import Game
from saveix.core.retention import apply_policy, apply_storage_limit
from saveix.core.store import ObjectStore


def retention_hook(config: Config, catalog: Catalog):
    """Called by the runner after each session; returns warnings to show the user."""

    def run(game: Game) -> list[str]:
        now = datetime.now(UTC)
        report = apply_policy(catalog, game, config.settings, now)
        storage = apply_storage_limit(
            catalog, ObjectStore(config.backup_root), config.settings, now
        )
        return report.warnings + storage.warnings

    return run


def prune(
    game: str | None = typer.Argument(None, help="Only this game; all games if left out."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only show what would be removed."),
) -> None:
    """Thin out old snapshots using the retention rules and limits."""
    config = Config()
    if config.settings.keep_all_snapshots:
        typer.echo("keep_all_snapshots is on; nothing is ever removed.")
        return
    now = datetime.now(UTC)
    with open_catalog(config) as catalog:
        games = [catalog.get_game(game)] if game else catalog.list_games()
        names = {g.id: g.name for g in catalog.list_games()}
        reports = [apply_policy(catalog, g, config.settings, now, dry_run) for g in games]
        if game is None:
            store = ObjectStore(config.backup_root)
            reports.append(apply_storage_limit(catalog, store, config.settings, now, dry_run))
    total = 0
    for report in reports:
        for removal in report.removals:
            total += 1
            name = names.get(removal.snapshot.game_id, "?")
            typer.echo(f"{name}: #{removal.snapshot.id} ({removal.reason})")
        for warning in report.warnings:
            typer.echo(f"warning: {warning}", err=True)
    verb = "Would remove" if dry_run else "Removed"
    typer.echo(f"{verb} {total} snapshots.")
