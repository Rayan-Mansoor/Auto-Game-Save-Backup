"""The launcher provider."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

from saveix.core.models import SourceKind
from saveix.core.paths import normalize
from saveix.core.providers import GameDetails, GameMatch, ProviderContext, SourceCandidate
from saveix.integrations.launchers.scan import (
    InstalledGame,
    default_epic_manifests,
    default_steam_root,
    epic_games,
    gog_games,
    steam_games,
    windows_gog_entries,
)


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", text.casefold())


class LauncherProvider:
    name = "launchers"
    description = "Games installed through Steam, the Epic Games Launcher and GOG on this PC"

    def __init__(
        self,
        context: ProviderContext,
        steam_root: Path | None = None,
        epic_manifests: Path | None = None,
        gog_entries: Callable[[], Iterable[dict]] = windows_gog_entries,
    ) -> None:
        self.steam_root = steam_root if steam_root is not None else default_steam_root()
        self.epic_manifests = epic_manifests or default_epic_manifests()
        self.gog_entries = gog_entries
        self._games: list[InstalledGame] | None = None

    def installed(self) -> list[InstalledGame]:
        if self._games is None:
            self._games = (
                steam_games(self.steam_root)
                + epic_games(self.epic_manifests)
                + gog_games(self.gog_entries)
            )
        return self._games

    def update(self, force: bool = False) -> str:
        self._games = None
        return f"found {len(self.installed())} installed games"

    def _match(self, game: InstalledGame) -> GameMatch:
        return GameMatch(
            self.name,
            f"{game.store}:{game.id}",
            game.name,
            steam_app_id=int(game.id) if game.store == "steam" and game.id.isdigit() else None,
            gog_id=int(game.id) if game.store == "gog" and game.id.isdigit() else None,
        )

    def search(self, query: str, limit: int = 10) -> list[GameMatch]:
        wanted = _norm(query)
        if not wanted:
            return []
        hits = [g for g in self.installed() if wanted in _norm(g.name)]
        hits.sort(key=lambda g: (_norm(g.name) != wanted, len(g.name)))
        return [self._match(g) for g in hits[:limit]]

    def lookup(
        self, steam_app_id: int | None = None, gog_id: int | None = None
    ) -> GameMatch | None:
        for game in self.installed():
            if steam_app_id and game.store == "steam" and game.id == str(steam_app_id):
                return self._match(game)
            if gog_id and game.store == "gog" and game.id == str(gog_id):
                return self._match(game)
        return None

    def details(self, match: GameMatch) -> GameDetails:
        game = next((g for g in self.installed() if f"{g.store}:{g.id}" == match.key), None)
        if game is None:
            return GameDetails(match)
        sources = []
        if game.store == "steam" and self.steam_root is not None:
            # Real Steam keeps cloud-synced files per user under userdata.
            remote = f"{normalize(self.steam_root)}/userdata/<userid>/{game.id}/remote"
            sources.append(SourceCandidate(SourceKind.FOLDER, remote))
        return GameDetails(
            match,
            sources=sources,
            executables=[game.executable] if game.executable else [],
            install_dir=game.install_dir,
        )
