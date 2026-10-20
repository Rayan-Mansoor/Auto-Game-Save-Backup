"""Check a provider's suggested save locations against this PC."""

from __future__ import annotations

from dataclasses import dataclass

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
