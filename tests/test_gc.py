import os
import time

from saveix.core.catalog import Catalog
from saveix.core.gc import GRACE_SECONDS, collect_garbage
from saveix.core.models import SnapshotFile, Trigger
from saveix.core.store import ObjectStore


def age(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_unused_contents_are_deleted_after_grace(tmp_path):
    store = ObjectStore(tmp_path / "b")
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("G")
        used, _ = store.put_bytes(b"used")
        unused, _ = store.put_bytes(b"unused" * 100)
        fresh, _ = store.put_bytes(b"just written")
        entry = SnapshotFile(None, "<appdata>/G", "<appdata>/G/s", used, 4, 0)
        catalog.add_snapshot(game, Trigger.MANUAL, "t", "f", [entry])
        for digest in (used, unused):
            age(store.path_for(digest), GRACE_SECONDS + 10)
        store.tmp.mkdir(parents=True, exist_ok=True)
        leftover = store.tmp / "x.part"
        leftover.write_bytes(b"partial")
        age(leftover, GRACE_SECONDS + 10)

        dry = collect_garbage(catalog, store, dry_run=True)
        assert dry.objects == 1 and store.exists(unused)

        report = collect_garbage(catalog, store)
        assert report.objects == 1 and report.bytes > 0
        assert store.exists(used) and store.exists(fresh) and not store.exists(unused)
        assert not leftover.exists()


def test_removed_snapshot_frees_its_contents(tmp_path):
    store = ObjectStore(tmp_path / "b")
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("G")
        digest, _ = store.put_bytes(b"old progress")
        entry = SnapshotFile(None, "<appdata>/G", "<appdata>/G/s", digest, 1, 0)
        snap = catalog.add_snapshot(game, Trigger.MANUAL, "t", "f", [entry])
        catalog.delete_snapshot(snap.id)
        report = collect_garbage(catalog, store, now=time.time() + GRACE_SECONDS + 1)
        assert report.objects == 1 and not store.exists(digest)


def test_reused_content_is_not_collected(tmp_path):
    store = ObjectStore(tmp_path / "b")
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        digest, _ = store.put_bytes(b"content")
        age(store.path_for(digest), GRACE_SECONDS + 10)
        # A backup stores the same content again but has not recorded its snapshot yet.
        store.put_bytes(b"content")
        assert collect_garbage(catalog, store).objects == 0
