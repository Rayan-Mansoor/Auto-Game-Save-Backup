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
    install_dir: str | None = None
    """The game's install folder on this PC; resolves ``<install>`` in source paths."""
    steam_app_id: int | None = None
    gog_id: int | None = None
    executables: list[str] = field(default_factory=list)
    """Executable names or full paths whose processes mean the game is running."""
    checkpoint_interval_minutes: int | None = None
    """Minimum minutes between checkpoints for this game; None uses the global setting."""
    sources: list[Source] = field(default_factory=list)


class Trigger(StrEnum):
    MANUAL = "manual"
    CHECKPOINT = "checkpoint"
    SESSION_END = "session_end"
    SAFETY = "safety"


@dataclass(frozen=True)
class SnapshotFile:
    source_id: int | None
    source_path: str
    template: str
    digest: str
    size: int
    mtime_ns: int


@dataclass
class Snapshot:
    id: int
    game_id: int
    created_at: str
    trigger: Trigger
    file_count: int
    total_size: int
    fingerprint: str
    label: str | None = None
    note: str | None = None
    session_id: int | None = None
    health: str | None = None
    """"ok" or "suspicious" once checked."""
    health_notes: list[str] = field(default_factory=list)


@dataclass
class Session:
    id: int
    game_id: int
    started_at: str
    ended_at: str | None = None
    crashed: bool = False
