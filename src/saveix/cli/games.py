"""`saveix game` and `saveix source` commands."""

from __future__ import annotations

from pathlib import Path

import typer

from saveix.cli.common import fail, open_catalog
from saveix.core.context import context_for
from saveix.core.models import Game, Source, SourceKind, SourceRole
from saveix.core.sources import SourceError, breadth_problem, guess_kind, to_template
from saveix.core.sources.registry import RegistryError, is_registry_path, normalize_key

game_app = typer.Typer(help="Manage the games saveix backs up.", no_args_is_help=True)
source_app = typer.Typer(help="Manage where a game keeps its saves.", no_args_is_help=True)


def print_sources(game: Game) -> None:
    if not game.sources:
        typer.echo("  (no sources yet; add one with `saveix source add`)")
    for s in game.sources:
        line = f"  [{s.id}] {s.kind.value:<8} {s.role.value:<6} {s.path}"
        if s.include:
            line += f"  include={','.join(s.include)}"
        if s.exclude:
            line += f"  exclude={','.join(s.exclude)}"
        if s.origin != "manual":
            line += f"  ({s.origin})"
        typer.echo(line)


@game_app.command("add")
def game_add(name: str) -> None:
    """Add a game to the library."""
    with open_catalog() as catalog:
        game = catalog.add_game(name)
    typer.echo(f"Added {game.name}.")


@game_app.command("list")
def game_list() -> None:
    """List all games."""
    with open_catalog() as catalog:
        games = catalog.list_games()
    if not games:
        typer.echo("No games yet; add one with `saveix game add NAME`.")
    for game in games:
        typer.echo(f"{game.name}  ({len(game.sources)} sources)")


@game_app.command("show")
def game_show(name: str) -> None:
    """Show a game and its save sources."""
    with open_catalog() as catalog:
        game = catalog.get_game(name)
    typer.echo(game.name)
    if game.install_dir:
        typer.echo(f"  installed in {game.install_dir}")
    print_sources(game)


@game_app.command("set-install")
def game_set_install(
    name: str,
    folder: str = typer.Argument("", help="The game's install folder; leave out to clear it."),
) -> None:
    """Tell saveix where a game is installed, for saves kept in its own folder."""
    install = None
    if folder:
        path = Path(folder).expanduser().absolute()
        if not path.is_dir():
            fail(f"'{folder}' is not a folder")
        install = str(path)
    with open_catalog() as catalog:
        target = catalog.get_game(name)
        catalog.set_install_dir(target, install)
    typer.echo(
        f"{target.name} is installed in {install}." if install else "Install folder cleared."
    )


@game_app.command("remove")
def game_remove(
    name: str, yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask to confirm.")
) -> None:
    """Remove a game from the library."""
    if not yes:
        typer.confirm(f"Remove {name} from the library?", abort=True)
    with open_catalog() as catalog:
        catalog.remove_game(name)
    typer.echo(f"Removed {name}.")


@source_app.command("add")
def source_add(
    game: str,
    path: str = typer.Argument(
        ..., help="Folder, file, glob pattern, placeholder template or HKCU registry key."
    ),
    kind: SourceKind | None = typer.Option(None, help="Detected from the path if omitted."),
    role: SourceRole = typer.Option(SourceRole.SAVE),
    include: list[str] = typer.Option([], help="Only back up files matching this pattern."),
    exclude: list[str] = typer.Option([], help="Skip files matching this pattern."),
    force: bool = typer.Option(False, help="Add even if the path looks too broad."),
) -> None:
    """Add a save location to a game."""
    if kind is SourceKind.REGISTRY or (kind is None and is_registry_path(path)):
        kind = SourceKind.REGISTRY
        try:
            template = normalize_key(path)
        except RegistryError as exc:
            fail(str(exc))
    with open_catalog() as catalog:
        target = catalog.get_game(game)
        if kind is not SourceKind.REGISTRY:
            context = context_for(target)
            template = to_template(path, context)
            if kind is None:
                try:
                    kind = guess_kind(context.expand(template))
                except (SourceError, ValueError) as exc:
                    fail(str(exc))
        problem = breadth_problem(template)
        if problem and not force:
            fail(f"{problem}. Use --force to add it anyway.")
        source = Source(kind, template, role, include=include, exclude=exclude)
        catalog.add_source(target, source)
    typer.echo(f"Added [{source.id}] {kind.value} {template} to {target.name}.")


@source_app.command("remove")
def source_remove(game: str, source_id: int) -> None:
    """Remove a save location from a game."""
    with open_catalog() as catalog:
        target = catalog.get_game(game)
        catalog.remove_source(target, source_id)
    typer.echo(f"Removed source {source_id} from {target.name}.")
