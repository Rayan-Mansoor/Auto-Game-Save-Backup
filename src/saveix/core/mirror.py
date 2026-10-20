"""Keep a second copy of all backups in another folder, such as a cloud drive.

Stored contents never change once written, so mirroring only copies what is new and
removes what was garbage-collected. The catalog is copied as a consistent snapshot.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from saveix.core.catalog import Catalog
from saveix.core.store import ObjectStore

CATALOG_NAME = "catalog.sqlite3"


@dataclass
class MirrorReport:
    copied: int = 0
    removed: int = 0
    bytes: int = 0


def _copy(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    shutil.copy2(source, tmp)
    os.replace(tmp, dest)


def mirror(catalog: Catalog, store: ObjectStore, target: Path) -> MirrorReport:
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    copy = ObjectStore(target)
    report = MirrorReport()
    wanted = set(store.digests())
    for digest in sorted(wanted):
        if not copy.exists(digest):
            _copy(store.path_for(digest), copy.path_for(digest))
            report.copied += 1
            report.bytes += store.stored_size(digest)
    for digest in list(copy.digests()):
        if digest not in wanted:
            copy.delete(digest)
            report.removed += 1

    tmp = target / (CATALOG_NAME + ".part")
    tmp.unlink(missing_ok=True)
    dest = sqlite3.connect(tmp)
    try:
        catalog.db.backup(dest)
    finally:
        dest.close()
    os.replace(tmp, target / CATALOG_NAME)
    return report
