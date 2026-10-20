"""The Ludusavi provider."""

from __future__ import annotations

from saveix.core.providers import GameDetails, GameMatch, ProviderContext
from saveix.integrations.ludusavi.download import Fetch, download_manifest, http_fetch


class LudusaviProvider:
    name = "ludusavi"
    description = "Ludusavi manifest: save locations for thousands of PC games (PCGamingWiki)"

    def __init__(self, context: ProviderContext, fetch: Fetch = http_fetch) -> None:
        self.folder = context.data_dir
        self.fetch = fetch

    @property
    def manifest_path(self):
        return self.folder / "manifest.yaml"

    def update(self, force: bool = False) -> str:
        changed = download_manifest(self.folder, self.fetch, force)
        return "downloaded the latest manifest" if changed else "already up to date"

    def search(self, query: str, limit: int = 10) -> list[GameMatch]:
        return []

    def lookup(
        self, steam_app_id: int | None = None, gog_id: int | None = None
    ) -> GameMatch | None:
        return None

    def details(self, match: GameMatch) -> GameDetails:
        return GameDetails(match)
