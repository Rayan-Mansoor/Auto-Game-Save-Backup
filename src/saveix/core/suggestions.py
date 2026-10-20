"""Check a provider's suggested save locations against this PC."""

from __future__ import annotations

from dataclasses import dataclass

from saveix.core.catalog import Catalog
from saveix.core.emulators import STEAM_REMOTE, Emulator, translate
from saveix.core.models import Game, Source, SourceKind
from saveix.core.paths import PathContext
from saveix.core.providers import GameDetails
from saveix.core.sources.registry import RegistryBackend
from saveix.core.sources.resolve import scan_source


@dataclass
class CheckedCandidate:
    source: Source
    files: int
    size: int
    note: str = ""

    @property
    def exists(self) -> bool:
        return self.files > 0


def check_candidates(
    details: GameDetails,
    game: Game,
    context: PathContext,
    emulators: list[Emulator],
    registry: RegistryBackend | None = None,
) -> list[CheckedCandidate]:
    """Turn suggestions into sources and see which ones hold files on this PC."""
    origin = f"provider:{details.match.provider}"
    steam_id = game.steam_app_id or details.match.steam_app_id
    checked = []
    for candidate in details.sources:
        paths = [(candidate.path, "")]
        if candidate.path.startswith(STEAM_REMOTE):
            if steam_id is None:
                continue
            paths = [
                (m.template, m.emulator.name)
                for m in translate(candidate.path, steam_id, context, emulators)
            ]
        for path, note in paths:
            source = Source(candidate.kind, path, candidate.role, origin=origin)
            if candidate.kind is SourceKind.REGISTRY:
                note = "registry key"
            scan = scan_source(source, context, registry)
            checked.append(CheckedCandidate(source, len(scan.files), scan.size, note))
    return checked


def apply_details(catalog: Catalog, game: Game, details: GameDetails) -> list[str]:
    """Fill in what the provider knows and the game does not yet; returns what changed."""
    changes = []
    if not game.install_dir and details.install_dir:
        catalog.set_install_dir(game, details.install_dir)
        changes.append(f"Installed in {details.install_dir}")
    if not game.steam_app_id and not game.gog_id:
        match = details.match
        if match.steam_app_id or match.gog_id:
            catalog.set_store_ids(game, match.steam_app_id, match.gog_id)
    if not game.executables and details.executables:
        catalog.set_executables(game, details.executables)
        changes.append(f"Executables: {', '.join(details.executables)}")
    if details.cloud_sync and not game.cloud_sync:
        catalog.set_cloud_sync(game, True)
        changes.append("This game can also sync saves through a cloud service.")
    return changes
