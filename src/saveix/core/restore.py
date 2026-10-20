"""Put a game's saves back to the state of any snapshot."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from saveix.core.backup import BackupEngine, NothingToBackUpError
from saveix.core.catalog import Catalog, CatalogError
from saveix.core.models import Game, Snapshot, SnapshotFile, Trigger
from saveix.core.paths import PathContext
from saveix.core.sources.resolve import scan_game
from saveix.core.store import CorruptObjectError, ObjectStore


class Action(StrEnum):
    WRITE = "write"
    DELETE = "delete"
    KEEP = "keep"


@dataclass(frozen=True)
class PlannedFile:
    action: Action
    template: str
    path: Path
    entry: SnapshotFile | None = None


@dataclass
class RestorePlan:
    game: Game
    snapshot: Snapshot
    files: list[PlannedFile] = field(default_factory=list)

    def of(self, action: Action) -> list[PlannedFile]:
        return [f for f in self.files if f.action is action]

    @property
    def has_changes(self) -> bool:
        return any(f.action is not Action.KEEP for f in self.files)


@dataclass
class RestoreResult:
    plan: RestorePlan
    safety_snapshot: Snapshot | None
    written: int = 0
    deleted: int = 0


def _digest_of(path: Path) -> str | None:
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while chunk := fh.read(1024 * 1024):
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


class Restorer:
    def __init__(self, catalog: Catalog, store: ObjectStore, engine: BackupEngine) -> None:
        self.catalog = catalog
        self.store = store
        self.engine = engine

    def plan(
        self,
        game: Game,
        snapshot: Snapshot,
        context: PathContext,
        remove_extra: bool = True,
    ) -> RestorePlan:
        if snapshot.game_id != game.id:
            raise CatalogError(f"Snapshot #{snapshot.id} does not belong to {game.name}")
        plan = RestorePlan(game, snapshot)
        wanted = self.catalog.snapshot_files(snapshot.id)
        current = {}
        for scan in scan_game(game, context):
            for found in scan.files:
                current[found.template] = found

        for entry in wanted:
            path = Path(context.expand(entry.template))
            found = current.get(entry.template)
            same = found and found.size == entry.size and _digest_of(path) == entry.digest
            plan.files.append(
                PlannedFile(Action.KEEP if same else Action.WRITE, entry.template, path, entry)
            )

        if remove_extra:
            # Files the game has now that did not exist at that stage, in the same sources.
            restored_sources = {e.source_path for e in wanted}
            wanted_templates = {e.template for e in wanted}
            for template, found in sorted(current.items()):
                source = next(s for s in game.sources if s.id == found.source_id)
                if template not in wanted_templates and source.path in restored_sources:
                    plan.files.append(PlannedFile(Action.DELETE, template, found.path))
        return plan

    def execute(self, plan: RestorePlan, context: PathContext) -> RestoreResult:
        # Check every stored copy first, so a damaged backup never leaves a half-restored game.
        for item in plan.of(Action.WRITE):
            if not self.store.verify(item.entry.digest):
                raise CorruptObjectError(
                    f"The backup copy of {item.template} is damaged; nothing was restored."
                )

        safety = None
        if plan.has_changes:
            try:
                backup = self.engine.backup(plan.game, context, Trigger.SAFETY)
                safety = backup.snapshot or backup.previous
            except NothingToBackUpError:
                pass

        result = RestoreResult(plan, safety)
        for item in plan.of(Action.WRITE):
            self.store.write_to(item.entry.digest, item.path)
            os.utime(item.path, ns=(item.entry.mtime_ns, item.entry.mtime_ns))
            result.written += 1
        for item in plan.of(Action.DELETE):
            item.path.unlink(missing_ok=True)
            result.deleted += 1
        return result
