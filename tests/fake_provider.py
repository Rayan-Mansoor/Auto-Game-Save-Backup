"""A provider used by tests, standing in for a real integration."""

from saveix.core.models import SourceKind, SourceRole
from saveix.core.providers import GameDetails, GameMatch, ProviderContext, SourceCandidate

GAMES = {
    "hk": GameMatch("fake", "hk", "Hollow Knight", steam_app_id=367520),
    "w3": GameMatch("fake", "w3", "The Witcher 3", steam_app_id=292030, gog_id=1495134320),
}


class FakeProvider:
    name = "fake"
    description = "Test provider"

    def __init__(self, context: ProviderContext):
        self.context = context
        self.updates = 0

    def update(self, force=False):
        self.updates += 1
        return "up to date"

    def search(self, query, limit=10):
        return [g for g in GAMES.values() if query.casefold() in g.name.casefold()][:limit]

    def lookup(self, steam_app_id=None, gog_id=None):
        for game in GAMES.values():
            if steam_app_id and game.steam_app_id == steam_app_id:
                return game
            if gog_id and game.gog_id == gog_id:
                return game
        return None

    def details(self, match):
        if match.key == "hk":
            return GameDetails(
                match,
                [
                    SourceCandidate(SourceKind.GLOB, "<locallow>/Team Cherry/Hollow Knight/*.dat"),
                    SourceCandidate(
                        SourceKind.REGISTRY,
                        "HKCU/Software/Team Cherry/Hollow Knight",
                        SourceRole.CONFIG,
                    ),
                    SourceCandidate(SourceKind.FOLDER, "<steamremote>"),
                ],
                executables=["hollow_knight.exe"],
                cloud_sync=True,
            )
        return GameDetails(
            match, [SourceCandidate(SourceKind.FOLDER, "<documents>/The Witcher 3/gamesaves")]
        )


def factory(context):
    return FakeProvider(context)
