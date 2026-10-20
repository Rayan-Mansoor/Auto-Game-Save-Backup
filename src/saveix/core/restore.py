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
from saveix.core.sources import registry as reg
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
    path: Path | None
    """The file to change; None for a registry key."""
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


CLOUD_WARNING = (
    "{name} also syncs its saves through a cloud service (such as Steam Cloud). After "
    "restoring, the service may offer its own copy or replace the restored saves. When it "
    "asks about a conflict, choose the local files. If it does not ask, start the game "
    "once with the cloud sync turned off or while offline so the restored saves are kept."
)


def cloud_warning(game: Game) -> str | None:
    return CLOUD_WARNING.format(name=game.name) if game.cloud_sync else None


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
        only_sources: set[int] | None = None,
    ) -> RestorePlan:
        """Work out what restoring would change; ``only_sources`` limits it to some sources."""
        if snapshot.game_id != game.id:
            raise CatalogError(f"Snapshot #{snapshot.id} does not belong to {game.name}")
        if only_sources:
            unknown = only_sources - {s.id for s in game.sources}
            if unknown:
                raise CatalogError(f"{game.name} has no source with id {min(unknown)}")
        plan = RestorePlan(game, snapshot)
        wanted = [
            entry
            for entry in self.catalog.snapshot_files(snapshot.id)
            if not only_sources or entry.source_id in only_sources
        ]
        current = {}
        for scan in scan_game(game, context, self.engine.registry):
            for found in scan.files:
                current[found.template] = found

        for entry in wanted:
            found = current.get(entry.template)
            if reg.key_from_template(entry.template):
                path = None
                same = found and hashlib.sha256(found.data).hexdigest() == entry.digest
            else:
                path = Path(context.expand(entry.template))
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
                if only_sources and source.id not in only_sources:
                    continue
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
        registry = self.engine.registry
        for item in plan.of(Action.WRITE):
            key = reg.key_from_template(item.template)
            if key:
                registry.write_tree(key, reg.deserialize(self.store.read_bytes(item.entry.digest)))
            else:
                self.store.write_to(item.entry.digest, item.path)
                os.utime(item.path, ns=(item.entry.mtime_ns, item.entry.mtime_ns))
            result.written += 1
        for item in plan.of(Action.DELETE):
            key = reg.key_from_template(item.template)
            if key:
                registry.delete_tree(key)
            else:
                item.path.unlink(missing_ok=True)
            result.deleted += 1
        return result
