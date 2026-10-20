"""`saveix prune` command and the retention hook used by the runner."""

from datetime import UTC, datetime

import typer

from saveix.cli.common import open_catalog
from saveix.core.catalog import Catalog
from saveix.core.config import Config
from saveix.core.models import Game
from saveix.core.retention import Removal
from saveix.core.retention import prune as prune_game


def apply_retention(config: Config, catalog: Catalog, game: Game, dry_run=False) -> list[Removal]:
    if config.settings.keep_all_snapshots:
        return []
    return prune_game(
        catalog, game, datetime.now(UTC), config.settings.recent_sessions_kept, dry_run
    )


def prune(
    game: str | None = typer.Argument(None, help="Only this game; all games if left out."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only show what would be removed."),
) -> None:
    """Thin out old snapshots using the retention rules."""
    config = Config()
    if config.settings.keep_all_snapshots:
        typer.echo("keep_all_snapshots is on; nothing is ever removed.")
        return
    with open_catalog(config) as catalog:
        games = [catalog.get_game(game)] if game else catalog.list_games()
        total = 0
        for target in games:
            for removal in apply_retention(config, catalog, target, dry_run):
                total += 1
                typer.echo(f"{target.name}: #{removal.snapshot.id} ({removal.reason})")
    verb = "Would remove" if dry_run else "Removed"
    typer.echo(f"{verb} {total} snapshots.")
