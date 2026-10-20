"""Provider plugins: optional, removable sources of known save locations.

The core never depends on any particular provider. Providers are found through the
``saveix.providers`` entry point group and are only loaded when the user enables
them in the ``providers`` setting. A provider answers in saveix's own terms
(placeholder templates, source kinds and roles), so swapping or removing one never
affects the rest of the app.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Protocol, runtime_checkable

from saveix.core.models import SourceKind, SourceRole

log = logging.getLogger("saveix")

ENTRY_POINT_GROUP = "saveix.providers"


@dataclass(frozen=True)
class GameMatch:
    provider: str
    key: str
    """The provider's own identifier for the game."""
    name: str
    steam_app_id: int | None = None
    gog_id: int | None = None


@dataclass(frozen=True)
class SourceCandidate:
    """A suggested save location, as a saveix template.

    ``<steamremote>`` stands for the game's Steam cloud folder; saveix translates
    it to emulator folders using the game's Steam app ID.
    """

    kind: SourceKind
    path: str
    role: SourceRole = SourceRole.SAVE


@dataclass
class GameDetails:
    match: GameMatch
    sources: list[SourceCandidate] = field(default_factory=list)
    executables: list[str] = field(default_factory=list)
    cloud_sync: bool | None = None


@dataclass(frozen=True)
class ProviderContext:
    data_dir: Path
    """A folder the provider may use for its own downloads and indexes."""


@runtime_checkable
class Provider(Protocol):
    name: str
    description: str

    def update(self, force: bool = False) -> str:
        """Refresh the provider's data; returns a short status message."""
        ...

    def search(self, query: str, limit: int = 10) -> list[GameMatch]: ...

    def lookup(
        self, steam_app_id: int | None = None, gog_id: int | None = None
    ) -> GameMatch | None: ...

    def details(self, match: GameMatch) -> GameDetails: ...


ProviderFactory = Callable[[ProviderContext], Provider]


def available_providers() -> dict[str, Callable[[], ProviderFactory]]:
    """Installed providers by name, whether enabled or not; each value imports its factory."""
    found: dict[str, Callable[[], ProviderFactory]] = {}
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        found[entry.name] = entry.load
    return found


def load_providers(enabled: list[str], data_dir: Path) -> list[Provider]:
    """Load the enabled providers; ones that are missing or broken are skipped."""
    installed = available_providers()
    providers = []
    for name in enabled:
        loader = installed.get(name)
        if loader is None:
            log.warning("provider %s is enabled but not installed", name)
            continue
        try:
            factory = loader()
            provider = factory(ProviderContext(data_dir / "providers" / name))
        except Exception:
            log.exception("provider %s could not be loaded", name)
            continue
        if not isinstance(provider, Provider):
            log.warning("provider %s does not implement the provider interface", name)
            continue
        providers.append(provider)
    return providers
