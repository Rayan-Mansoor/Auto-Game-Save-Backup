"""`saveix emulators` command."""

import typer

from saveix.cli.common import fail, open_catalog
from saveix.core.catalog import CatalogError
from saveix.core.config import Config
from saveix.core.context import context_for
from saveix.core.emulators import find_remote_folders, load_emulators
from saveix.core.models import Source, SourceKind


def emulators(
    game: str,
    add: bool = typer.Option(False, "--add", help="Add the folders found as save sources."),
) -> None:
    """Find a game's saves in Steam emulator folders (needs its Steam app ID)."""
    config = Config()
    with open_catalog(config) as catalog:
        target = catalog.get_game(game)
        if not target.steam_app_id:
            fail(f"{target.name} has no Steam app ID; run `saveix identify FOLDER --game` first.")
        known = load_emulators(config.dirs.config_dir / "emulators.json")
        matches = find_remote_folders(target.steam_app_id, context_for(target), known)
        if not matches:
            typer.echo(f"No emulator save folders found for app {target.steam_app_id}.")
            return
        for match in matches:
            typer.echo(f"{match.emulator.name}: {match.template}")
            if add:
                source = Source(SourceKind.FOLDER, match.template, origin="emulator")
                try:
                    catalog.add_source(target, source)
                    typer.echo("  added")
                except CatalogError:
                    typer.echo("  already a source")
