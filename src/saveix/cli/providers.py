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
