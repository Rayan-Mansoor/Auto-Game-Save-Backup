"""Delete stored contents that no snapshot refers to any more."""

from __future__ import annotations

import time
from dataclasses import dataclass

from saveix.core.catalog import Catalog
from saveix.core.store import ObjectStore

GRACE_SECONDS = 3600
"""Recently written contents are left alone: a backup may be about to record them."""


@dataclass
class GarbageReport:
    objects: int = 0
    bytes: int = 0


def collect_garbage(
    catalog: Catalog, store: ObjectStore, dry_run: bool = False, now: float | None = None
) -> GarbageReport:
    now = time.time() if now is None else now
    referenced = set(catalog.digest_use_counts())
    report = GarbageReport()
    for digest in list(store.digests()):
        if digest in referenced:
            continue
        path = store.path_for(digest)
        try:
            stat = path.stat()
        except OSError:
            continue
        if now - stat.st_mtime < GRACE_SECONDS:
            continue
        report.objects += 1
        report.bytes += stat.st_size
        if not dry_run:
            store.delete(digest)
    # Leftovers from copies that were interrupted.
    if store.tmp.exists():
        for part in store.tmp.glob("*.part"):
            try:
                if now - part.stat().st_mtime >= GRACE_SECONDS and not dry_run:
                    part.unlink()
            except OSError:
                continue
    return report
