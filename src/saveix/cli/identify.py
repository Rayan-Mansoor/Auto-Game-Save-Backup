"""`saveix identify` command."""

from pathlib import Path

import typer

from saveix.cli.common import fail, open_catalog
from saveix.core.identify import identify as identify_folder


def identify(
    folder: Path,
    game: str | None = typer.Option(
        None, "--game", "-g", help="Store what was found on this game (and its install folder)."
    ),
) -> None:
    """Find out which game an install folder holds from the files shipped with it."""
    folder = folder.expanduser().absolute()
    if not folder.is_dir():
        fail(f"'{folder}' is not a folder")
    result = identify_folder(folder)
    if not result.found:
        fail("No Steam app ID or GOG ID found in that folder.")
    if result.name:
        typer.echo(f"Name: {result.name}")
    if result.steam_app_id:
        typer.echo(f"Steam app ID: {result.steam_app_id}")
    if result.gog_id:
        typer.echo(f"GOG ID: {result.gog_id}")
    for path in result.evidence:
        typer.echo(f"  from {path.relative_to(folder)}")
    if game:
        with open_catalog() as catalog:
            target = catalog.get_game(game)
            catalog.set_store_ids(target, result.steam_app_id, result.gog_id)
            if not target.install_dir:
                catalog.set_install_dir(target, str(folder))
        typer.echo(f"Saved on {target.name}.")
