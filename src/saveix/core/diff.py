"""Compare the files of two snapshots, or a snapshot and the files on disk."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from saveix.core.models import SnapshotFile


class Change(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass(frozen=True)
class FileChange:
    change: Change
    template: str
    old_size: int | None
    new_size: int | None


def diff_files(old: list[SnapshotFile], new: list[SnapshotFile]) -> list[FileChange]:
    before = {f.template: f for f in old}
    after = {f.template: f for f in new}
    changes = []
    for template in sorted(before.keys() | after.keys()):
        a, b = before.get(template), after.get(template)
        if a is None:
            changes.append(FileChange(Change.ADDED, template, None, b.size))
        elif b is None:
            changes.append(FileChange(Change.REMOVED, template, a.size, None))
        elif a.digest != b.digest:
            changes.append(FileChange(Change.MODIFIED, template, a.size, b.size))
    return changes
