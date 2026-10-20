"""Provider that finds games installed through Steam, the Epic Games Launcher and GOG.

It knows nothing about save files; it tells saveix where games are installed, their
store IDs and executables, and where real Steam keeps a game's cloud files.
"""

from __future__ import annotations

from saveix.core.providers import ProviderContext
from saveix.integrations.launchers.provider import LauncherProvider


def create(context: ProviderContext) -> LauncherProvider:
    return LauncherProvider(context)
