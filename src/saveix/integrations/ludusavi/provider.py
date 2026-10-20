"""The Ludusavi provider."""

from __future__ import annotations

from pathlib import Path

from saveix.core.providers import GameDetails, GameMatch, ProviderContext
from saveix.integrations.ludusavi.download import Fetch, download_manifest, http_fetch
from saveix.integrations.ludusavi.index import ManifestIndex, build_index, index_is_current


class LudusaviProvider:
    name = "ludusavi"
    description = "Ludusavi manifest: save locations for thousands of PC games (PCGamingWiki)"

    def __init__(self, context: ProviderContext, fetch: Fetch = http_fetch) -> None:
        self.folder = context.data_dir
        self.fetch = fetch
        self._index: ManifestIndex | None = None

    @property
    def manifest_path(self) -> Path:
        return self.folder / "manifest.yaml"

    @property
    def index_path(self) -> Path:
        return self.folder / "index.sqlite3"

    def update(self, force: bool = False) -> str:
        changed = download_manifest(self.folder, self.fetch, force)
        if changed or not index_is_current(self.manifest_path, self.index_path):
            self._close_index()
            count = build_index(self.manifest_path, self.index_path)
            return f"downloaded the latest manifest ({count} games with save locations)"
        return "already up to date"

    def _close_index(self) -> None:
        if self._index is not None:
            self._index.close()
            self._index = None

    def index(self) -> ManifestIndex | None:
        if self._index is None:
            if not self.manifest_path.exists():
                return None
            if not index_is_current(self.manifest_path, self.index_path):
                build_index(self.manifest_path, self.index_path)
            self._index = ManifestIndex(self.index_path)
        return self._index

    def _match(self, index: ManifestIndex, name: str) -> GameMatch:
        entry = index.entry(name) or {}
        return GameMatch(
            self.name,
            name,
            name,
            steam_app_id=(entry.get("steam") or {}).get("id"),
            gog_id=(entry.get("gog") or {}).get("id"),
        )

    def search(self, query: str, limit: int = 10) -> list[GameMatch]:
        index = self.index()
        if index is None:
            return []
        return [self._match(index, name) for name in index.search(query, limit)]

    def lookup(
        self, steam_app_id: int | None = None, gog_id: int | None = None
    ) -> GameMatch | None:
        index = self.index()
        if index is None:
            return None
        name = None
        if steam_app_id:
            name = index.by_store_id("steam", steam_app_id)
        if name is None and gog_id:
            name = index.by_store_id("gog", gog_id)
        return self._match(index, name) if name else None

    def details(self, match: GameMatch) -> GameDetails:
        return GameDetails(match)
