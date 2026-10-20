"""`saveix detect` command."""

import threading

import typer

from saveix.cli.common import open_catalog
from saveix.core.catalog import CatalogError
from saveix.core.config import Config
from saveix.core.context import context_for
from saveix.core.detect import ChangeRecorder, detection_roots, suggest
from saveix.core.models import Source, SourceKind
from saveix.core.watcher import WatchdogWatcher

MAX_SUGGESTIONS = 5


def detect(
    game: str,
    seconds: int = typer.Option(
        0, help="Stop after this many seconds instead of waiting for Enter."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Add every suggestion without asking."),
) -> None:
    """Find a game's save folders by watching what it writes while you play."""
    config = Config()
    with open_catalog(config) as catalog:
        target = catalog.get_game(game)
    context = context_for(target)
    recorder = ChangeRecorder(ignore=[config.dirs.data_dir, config.backup_root])
    watcher = WatchdogWatcher()
    watcher.start(detection_roots(context), recorder)
    try:
        if seconds:
            typer.echo(f"Watching for {seconds} seconds: play {target.name} and save once.")
            threading.Event().wait(seconds)
        else:
            typer.echo(f"Watching. Start {target.name}, play until it saves, then quit the game.")
            typer.prompt("Press Enter when done", default="", show_default=False)
    finally:
        watcher.stop()

    suggestions = suggest(recorder.paths(), context, target.name)[:MAX_SUGGESTIONS]
    if not suggestions:
        typer.echo("No likely save files were written. Try again and make sure the game saves.")
        return
    with open_catalog(config) as catalog:
        target = catalog.get_game(game)
        for item in suggestions:
            typer.echo(f"{item.template}  ({len(item.files)} files changed)")
            for name in item.files[:5]:
                typer.echo(f"    {name}")
            if yes or typer.confirm("  Add this as a save source?", default=False):
                try:
                    catalog.add_source(
                        target, Source(SourceKind.FOLDER, item.template, origin="detected")
                    )
                    typer.echo("  added")
                except CatalogError as exc:
                    typer.echo(f"  {exc}")
