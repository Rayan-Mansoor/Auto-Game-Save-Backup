"""Notice save writes during a session and decide when a checkpoint is due.

Games write saves in bursts (temporary file, rename, several slot files), so a
checkpoint is only taken once the save folders have been quiet for a while.
"""

from __future__ import annotations

import fnmatch
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from saveix.core.models import Game, Source, SourceKind
from saveix.core.paths import PathContext, UnresolvedPlaceholderError, normalize
from saveix.core.sources import has_glob
from saveix.core.sources.resolve import matches


def watch_root(source: Source, context: PathContext) -> Path | None:
    """The folder to watch for a source: its path up to the first wildcard."""
    if source.kind is SourceKind.REGISTRY:
        return None
    try:
        expanded = context.expand(source.path)
    except UnresolvedPlaceholderError:
        return None
    parts = expanded.split("/")
    fixed = []
    for part in parts:
        if has_glob(part):
            break
        fixed.append(part)
    root = Path("/".join(fixed) or "/")
    if source.kind is SourceKind.FILE or (root.exists() and root.is_file()):
        root = root.parent
    while not root.exists():
        if root.parent == root:
            return None
        root = root.parent
    return root


def source_covers(source: Source, context: PathContext, path: str) -> bool:
    """Whether a changed path belongs to a source, honouring its filters."""
    if source.kind is SourceKind.REGISTRY:
        return False
    try:
        expanded = context.expand(source.path)
    except UnresolvedPlaceholderError:
        return False
    target = normalize(path)
    folded, pattern = target.casefold(), expanded.casefold()
    relative = None
    if source.kind is SourceKind.GLOB or has_glob(pattern):
        candidate = folded
        while True:
            if fnmatch.fnmatch(candidate, pattern):
                relative = target[len(candidate) :].lstrip("/") or target.rsplit("/", 1)[-1]
                break
            parent = candidate.rsplit("/", 1)[0]
            if parent == candidate or not parent:
                return False
            candidate = parent
    elif folded == pattern:
        relative = target.rsplit("/", 1)[-1]
    elif folded.startswith(pattern.rstrip("/") + "/"):
        relative = target[len(pattern.rstrip("/")) + 1 :]
    else:
        return False
    if source.include and not any(matches(p, relative) for p in source.include):
        return False
    return not any(matches(p, relative) for p in source.exclude)


class ChangeTracker:
    """Collects save changes and says when they have settled into a checkpoint."""

    def __init__(self, game: Game, context: PathContext, quiet_period: float) -> None:
        self.game = game
        self.context = context
        self.quiet_period = quiet_period
        self._lock = threading.Lock()
        self._last_change: float | None = None

    def record(self, path: str, now: float) -> bool:
        """Note a changed path; returns whether it belongs to one of the game's sources."""
        if not any(source_covers(s, self.context, path) for s in self.game.sources):
            return False
        with self._lock:
            self._last_change = now
        return True

    def pending(self) -> bool:
        with self._lock:
            return self._last_change is not None

    def due(self, now: float) -> bool:
        with self._lock:
            return self._last_change is not None and now - self._last_change >= self.quiet_period

    def reset(self) -> None:
        with self._lock:
            self._last_change = None


class FolderWatcher(Protocol):
    def start(self, folders: list[Path], on_change: Callable[[str], None]) -> None: ...

    def stop(self) -> None: ...


class WatchdogWatcher:
    """Watches folders recursively with the operating system's change notifications."""

    def __init__(self) -> None:
        self._observer = None

    def start(self, folders: list[Path], on_change: Callable[[str], None]) -> None:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event) -> None:
                if event.event_type in ("opened", "closed_no_write"):
                    return
                if event.is_directory and event.event_type == "modified":
                    return
                on_change(str(event.src_path))
                if getattr(event, "dest_path", ""):
                    on_change(str(event.dest_path))

        observer = Observer()
        handler = Handler()
        for folder in dict.fromkeys(folders):
            observer.schedule(handler, str(folder), recursive=True)
        observer.daemon = True
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None


def watch_game(
    game: Game,
    context: PathContext,
    tracker: ChangeTracker,
    watcher: FolderWatcher,
    clock: Callable[[], float],
) -> list[Path]:
    """Start watching a game's save folders, feeding changes into the tracker."""
    roots = [r for r in (watch_root(s, context) for s in game.sources) if r is not None]
    # Watching a folder also covers everything inside it.
    roots = sorted(set(roots), key=lambda p: len(p.parts))
    distinct: list[Path] = []
    for root in roots:
        if not any(root == d or d in root.parents for d in distinct):
            distinct.append(root)
    if distinct:
        watcher.start(distinct, lambda path: tracker.record(path, clock()))
    return distinct
