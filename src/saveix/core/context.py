"""Build the path context for a particular game on this PC."""

from __future__ import annotations

from pathlib import Path

from saveix.core.models import Game
from saveix.core.paths import PathContext


def context_for(game: Game) -> PathContext:
    install = Path(game.install_dir) if game.install_dir else None
    return PathContext.for_system(install=install)
