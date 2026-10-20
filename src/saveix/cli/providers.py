"""`saveix providers` and `saveix search` commands."""

import typer

from saveix.cli.common import fail
from saveix.core.config import Config
from saveix.core.providers import Provider, available_providers, load_providers

app = typer.Typer(help="Optional databases of known save locations.", no_args_is_help=True)


def enabled_providers(config: Config) -> list[Provider]:
    return load_providers(config.settings.providers, config.dirs.data_dir)


@app.command("list")
def providers_list() -> None:
    """Show installed providers and which are enabled."""
    config = Config()
    installed = available_providers()
    if not installed:
        typer.echo("No providers are installed.")
    for name in sorted(installed):
        state = "enabled" if name in config.settings.providers else "disabled"
        typer.echo(f"{name}  ({state})")


@app.command("enable")
def providers_enable(name: str) -> None:
    """Turn on a provider."""
    config = Config()
    if name not in available_providers():
        fail(f"No provider named '{name}' is installed.")
    if name not in config.settings.providers:
        config.settings.providers.append(name)
        config.save()
    typer.echo(f"{name} enabled. Run `saveix providers update` to download its data.")


@app.command("disable")
def providers_disable(name: str) -> None:
    """Turn off a provider. Games already set up keep their save sources."""
    config = Config()
    if name not in config.settings.providers:
        fail(f"{name} is not enabled.")
    config.settings.providers.remove(name)
    config.save()
    typer.echo(f"{name} disabled.")


@app.command("update")
def providers_update(
    force: bool = typer.Option(False, help="Download again even if nothing changed."),
) -> None:
    """Refresh the data of every enabled provider."""
    providers = enabled_providers(Config())
    if not providers:
        fail("No providers are enabled.")
    for provider in providers:
        try:
            typer.echo(f"{provider.name}: {provider.update(force)}")
        except Exception as exc:
            typer.echo(f"{provider.name}: update failed: {exc}", err=True)


def search(
    query: str,
    limit: int = typer.Option(10, "--limit", "-n"),
) -> None:
    """Search enabled providers for a game."""
    providers = enabled_providers(Config())
    if not providers:
        fail("No providers are enabled; see `saveix providers list`.")
    found = False
    for provider in providers:
        for match in provider.search(query, limit):
            found = True
            ids = []
            if match.steam_app_id:
                ids.append(f"Steam {match.steam_app_id}")
            if match.gog_id:
                ids.append(f"GOG {match.gog_id}")
            extra = f"  ({', '.join(ids)})" if ids else ""
            typer.echo(f"[{provider.name}] {match.name}{extra}")
    if not found:
        typer.echo("No matches.")


def suggest(
    game: str,
    query: str | None = typer.Option(None, help="Name to search for; defaults to the game name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Add every location found without asking."),
) -> None:
    """Set up a game from provider data: suggest save locations and add the ones you confirm."""
    from saveix.cli.common import open_catalog
    from saveix.cli.scan import human_size
    from saveix.core.catalog import CatalogError
    from saveix.core.context import context_for
    from saveix.core.emulators import load_emulators
    from saveix.core.suggestions import check_candidates

    config = Config()
    providers = enabled_providers(config)
    if not providers:
        fail("No providers are enabled; see `saveix providers list`.")
    with open_catalog(config) as catalog:
        target = catalog.get_game(game)
        match, provider = None, None
        for provider in providers:
            if target.steam_app_id or target.gog_id:
                match = provider.lookup(target.steam_app_id, target.gog_id)
            if match is None:
                matches = provider.search(query or target.name, limit=5)
                if len(matches) > 1 and not yes:
                    for number, item in enumerate(matches, 1):
                        typer.echo(f"  {number}. {item.name}")
                    choice = typer.prompt("Which one is it? (0 for none)", type=int, default=1)
                    match = matches[choice - 1] if 0 < choice <= len(matches) else None
                elif matches:
                    match = matches[0]
            if match:
                break
        if match is None:
            fail(f"No provider knows {target.name}; try --query or `saveix detect`.")

        typer.echo(f"Found {match.name} in {provider.name}.")
        details = provider.details(match)
        emulators = load_emulators(config.dirs.config_dir / "emulators.json")
        checked = check_candidates(details, target, context_for(target), emulators)
        if not checked:
            typer.echo("The provider lists no usable save locations for Windows.")
        for item in checked:
            s = item.source
            where = (
                f"{item.files} files, {human_size(item.size)}" if item.exists else "not on this PC"
            )
            note = f", {item.note}" if item.note else ""
            typer.echo(f"{s.role.value:<6} {s.path}  ({where}{note})")
            if not item.exists:
                continue
            if yes or typer.confirm("  Add this location?", default=True):
                try:
                    catalog.add_source(target, s)
                    typer.echo("  added")
                except CatalogError as exc:
                    typer.echo(f"  {exc}")

        if not target.steam_app_id and not target.gog_id:
            catalog.set_store_ids(target, match.steam_app_id, match.gog_id)
        if not target.executables and details.executables:
            catalog.set_executables(target, details.executables)
            typer.echo(f"Executables: {', '.join(details.executables)}")
        if details.cloud_sync and not target.cloud_sync:
            catalog.set_cloud_sync(target, True)
            typer.echo("This game can also sync saves through a cloud service.")
