"""Neutral data types shared across the core."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceKind(StrEnum):
    FOLDER = "folder"
    FILE = "file"
    GLOB = "glob"
    REGISTRY = "registry"


class SourceRole(StrEnum):
    SAVE = "save"
    CONFIG = "config"


MANUAL = "manual"


@dataclass
class Source:
    """One place where a game keeps part of its saved data."""

    kind: SourceKind
    path: str
    role: SourceRole = SourceRole.SAVE
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    origin: str = MANUAL
    id: int | None = None
    game_id: int | None = None


@dataclass
class Game:
    name: str
    id: int | None = None
    sources: list[Source] = field(default_factory=list)
