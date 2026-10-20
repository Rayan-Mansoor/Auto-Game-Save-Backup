"""Assisted detection: suggest save locations from the files a game writes.

While the user plays and saves once, every file change in the usual save folders
(and the game's install folder) is recorded. Noise such as logs, caches and crash
dumps is dropped, and the remaining changes are grouped into one suggested folder
per game folder, ranked by how much they look like saves.
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from saveix.core.paths import (
    APPDATA,
    DOCUMENTS,
    INSTALL,
    LOCALAPPDATA,
    LOCALLOW,
    PROGRAMDATA,
    PUBLIC,
    SAVEDGAMES,
    PathContext,
    normalize,
)

WATCHED_FOLDERS = (APPDATA, LOCALAPPDATA, LOCALLOW, DOCUMENTS, SAVEDGAMES, PUBLIC, PROGRAMDATA)

NOISE_EXTENSIONS = {
    ".log", ".dmp", ".mdmp", ".tmp", ".etl", ".lock", ".pf", ".db-journal", ".db-wal",
    ".ldb", ".cache", ".crdownload", ".part",
}  # fmt: skip
NOISE_FOLDERS = {
    "cache", "caches", "shadercache", "gpucache", "dxcache", "d3dscache", "glcache",
    "nvidia", "crashdumps", "crashes", "crashreport", "logs", "temp", "tmp", "inetcache",
    "code cache", "webcache", "htmlcache", "pipelinecache",
}  # fmt: skip
NOISE_TOP_FOLDERS = {
    "microsoft", "packages", "google", "mozilla", "discord", "steam", "epicgameslauncher",
    "nvidia corporation", "amd", "intel", "slack", "spotify", "onedrive", "zoom", "saveix",
}  # fmt: skip
"""Folders right below a system folder that belong to other software."""

SAVE_HINTS = re.compile(r"(save|slot|profile|progress|player|user|persistent|\.sav$|\.dat$)", re.I)

DEEPER_ROOTS = {LOCALLOW: 2, DOCUMENTS: 1, SAVEDGAMES: 1}
"""How many folder levels identify one game under each root (LocalLow is Company/Game)."""


@dataclass
class Suggestion:
    template: str
    files: list[str] = field(default_factory=list)
    score: float = 0.0


def is_noise(template: str) -> bool:
    parts = template.split("/")
    name = parts[-1].casefold()
    if any(name.endswith(ext) for ext in NOISE_EXTENSIONS) or name in ("desktop.ini", "thumbs.db"):
        return True
    folders = [p.casefold() for p in parts[1:-1]]
    if folders and folders[0] in NOISE_TOP_FOLDERS:
        return True
    return any(f in NOISE_FOLDERS for f in folders)


def _game_folder(template: str) -> str | None:
    """The folder that identifies one game, e.g. ``<locallow>/Team Cherry/Hollow Knight``."""
    parts = template.split("/")
    root = parts[0]
    if not (root.startswith("<") and root.endswith(">")):
        return None
    depth = DEEPER_ROOTS.get(root, 1)
    if root == DOCUMENTS and len(parts) > 3 and parts[1].casefold() == "my games":
        depth = 2
    if root == INSTALL:
        depth = 1
    if len(parts) - 1 <= depth:
        # The file sits directly in the root or the game folder level itself.
        return "/".join(parts[:-1]) if len(parts) > 2 else None
    return "/".join(parts[: depth + 1])


def _common_folder(files: list[str]) -> str:
    split = [f.split("/")[:-1] for f in files]
    common = []
    for level in zip(*split, strict=False):
        if all(p == level[0] for p in level):
            common.append(level[0])
        else:
            break
    return "/".join(common)


def suggest(changed: list[str], context: PathContext, game_name: str = "") -> list[Suggestion]:
    """Group changed real paths into suggested save folders, best first."""
    groups: dict[str, set[str]] = defaultdict(set)
    for path in changed:
        template = context.collapse(path)
        if is_noise(template):
            continue
        folder = _game_folder(template)
        if folder:
            groups[folder].add(template)

    words = {w for w in re.split(r"[^a-z0-9]+", game_name.casefold()) if len(w) > 2}
    suggestions = []
    for folder, files in groups.items():
        files_sorted = sorted(files)
        common = _common_folder(files_sorted)
        template = common if len(common) > len(folder) else folder
        score = float(len(files))
        score += 3 * sum(1 for f in files if SAVE_HINTS.search(f.rsplit("/", 1)[-1]))
        if words and any(w in template.casefold().replace(" ", "") for w in words):
            score += 10
        if SAVE_HINTS.search(template.rsplit("/", 1)[-1]):
            score += 5
        suggestions.append(Suggestion(template, files_sorted, score))
    return sorted(suggestions, key=lambda s: (-s.score, s.template))


class ChangeRecorder:
    """Collects changed file paths from a folder watcher (thread-safe)."""

    def __init__(self, ignore: list[Path] | None = None) -> None:
        self._lock = threading.Lock()
        self._paths: set[str] = set()
        self._ignore = [normalize(p).casefold().rstrip("/") + "/" for p in ignore or []]

    def __call__(self, path: str) -> None:
        text = normalize(path)
        if any(text.casefold().startswith(prefix) for prefix in self._ignore):
            return
        if Path(text).is_dir():
            return
        with self._lock:
            self._paths.add(text)

    def paths(self) -> list[str]:
        with self._lock:
            return sorted(self._paths)


def detection_roots(context: PathContext) -> list[Path]:
    values = context.values()
    roots = [Path(values[name]) for name in WATCHED_FOLDERS if name in values]
    if context.install is not None:
        roots.append(context.install)
    return [r for r in dict.fromkeys(roots) if r.is_dir()]
