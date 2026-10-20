"""Snapshot engine: captures all of a game's sources together."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from saveix.core.catalog import Catalog
from saveix.core.models import Game, Snapshot, SnapshotFile, Trigger
from saveix.core.paths import PathContext
from saveix.core.sources.registry import RegistryBackend, system_registry
from saveix.core.sources.resolve import FoundFile, scan_game
from saveix.core.store import ObjectStore

READ_ATTEMPTS = 3


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def fingerprint(files: list[SnapshotFile]) -> str:
    """Identify a snapshot's content regardless of when it was taken."""
    hasher = hashlib.sha256()
    for f in sorted(files, key=lambda f: f.template):
        hasher.update(f"{f.template}\0{f.digest}\n".encode())
    return hasher.hexdigest()


class NothingToBackUpError(Exception):
    pass


@dataclass
class BackupResult:
    snapshot: Snapshot | None
    """The new snapshot, or None when nothing changed since the previous one."""
    previous: Snapshot | None
    changed_files: int = 0
    """Files that are new or differ from the previous snapshot."""
    skipped: list[tuple[str, str]] = field(default_factory=list)
    """Files that could not be read, with the reason."""
    source_errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def unchanged(self) -> bool:
        return self.snapshot is None


class BackupEngine:
    def __init__(
        self,
        catalog: Catalog,
        store: ObjectStore,
        clock: Callable[[], str] = utc_now,
        retry_delay: float = 0.5,
        registry: RegistryBackend | None = None,
    ) -> None:
        self.catalog = catalog
        self.store = store
        self.registry = registry or system_registry()
        self.clock = clock
        self.retry_delay = retry_delay

    def backup(self, game: Game, context: PathContext, trigger: Trigger) -> BackupResult:
        previous = self.catalog.latest_snapshot(game)
        known = {}
        if previous:
            known = {f.template: f for f in self.catalog.snapshot_files(previous.id)}

        result = BackupResult(snapshot=None, previous=previous)
        captured: list[SnapshotFile] = []
        for scan in scan_game(game, context, self.registry):
            if scan.error:
                result.source_errors.append((scan.source.path, scan.error))
            for found in scan.files:
                entry = self._capture(found, scan.source.path, known.get(found.template), result)
                if entry:
                    captured.append(entry)

        if not captured:
            raise NothingToBackUpError(f"No save files found for {game.name}")
        content = fingerprint(captured)
        if previous and previous.fingerprint == content:
            return result
        result.snapshot = self.catalog.add_snapshot(game, trigger, self.clock(), content, captured)
        return result

    def _capture(
        self,
        found: FoundFile,
        source_path: str,
        known: SnapshotFile | None,
        result: BackupResult,
    ) -> SnapshotFile | None:
        if found.data is not None:
            digest, size = self.store.put_bytes(found.data)
            if known is None or known.digest != digest:
                result.changed_files += 1
            return SnapshotFile(found.source_id, source_path, found.template, digest, size, 0)

        # A file with the same size and modification time as last time is not re-read.
        if (
            known
            and known.size == found.size
            and known.mtime_ns == found.mtime_ns
            and self.store.exists(known.digest)
        ):
            return SnapshotFile(
                found.source_id,
                source_path,
                found.template,
                known.digest,
                found.size,
                found.mtime_ns,
            )

        reason = "unknown error"
        for attempt in range(READ_ATTEMPTS):
            if attempt:
                time.sleep(self.retry_delay)
            try:
                before = found.path.stat()
                digest, size = self.store.put_file(found.path)
                after = found.path.stat()
            except FileNotFoundError:
                reason = "file disappeared"
                break
            except OSError as exc:
                reason = f"could not read: {exc.strerror or exc}"
                continue
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                reason = "file kept changing while being copied"
                continue
            if known is None or known.digest != digest:
                result.changed_files += 1
            return SnapshotFile(
                found.source_id, source_path, found.template, digest, size, after.st_mtime_ns
            )
        if known and self.store.exists(known.digest):
            # Keep the last good copy rather than making the file look deleted.
            result.skipped.append((found.template, f"{reason}; kept the previous version"))
            return SnapshotFile(
                found.source_id,
                source_path,
                found.template,
                known.digest,
                known.size,
                known.mtime_ns,
            )
        result.skipped.append((found.template, reason))
        return None
