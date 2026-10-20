import itertools
import os

import pytest
from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.backup import BackupEngine, NothingToBackUpError
from saveix.core.catalog import Catalog
from saveix.core.models import Source, SourceKind, Trigger
from saveix.core.store import ObjectStore

runner = CliRunner()


@pytest.fixture
def saves(fake_home):
    root = fake_home / "AppData" / "Roaming" / "G"
    root.mkdir(parents=True)
    (root / "slot1.sav").write_bytes(b"level 1")
    (root / "profile.dat").write_bytes(b"unlocks")
    return root


@pytest.fixture
def setup(tmp_path, saves):
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    game = catalog.add_game("G")
    catalog.add_source(game, Source(SourceKind.FOLDER, "<appdata>/G"))
    counter = itertools.count(1)
    engine = BackupEngine(
        catalog,
        ObjectStore(tmp_path / "backups"),
        clock=lambda: f"2026-01-01T00:00:{next(counter):02d}Z",
        retry_delay=0,
    )
    yield catalog, game, engine
    catalog.close()


def touch_later(path, data):
    """Write new content and make sure the modification time moves forward."""
    old = path.stat().st_mtime_ns
    path.write_bytes(data)
    os.utime(path, ns=(old + 10**9, old + 10**9))


def test_first_backup_captures_all_sources(setup, context, fake_home):
    catalog, game, engine = setup
    other = fake_home / "Documents" / "G.ini"
    other.write_text("cfg")
    catalog.add_source(game, Source(SourceKind.FILE, "<documents>/G.ini"))

    result = engine.backup(game, context, Trigger.MANUAL)

    snap = result.snapshot
    assert snap.file_count == 3 and snap.trigger is Trigger.MANUAL
    assert result.changed_files == 3
    templates = [f.template for f in catalog.snapshot_files(snap.id)]
    assert templates == ["<appdata>/G/profile.dat", "<appdata>/G/slot1.sav", "<documents>/G.ini"]


def test_unchanged_saves_create_no_snapshot(setup, context):
    catalog, game, engine = setup
    first = engine.backup(game, context, Trigger.MANUAL).snapshot
    again = engine.backup(game, context, Trigger.CHECKPOINT)

    assert again.unchanged and again.previous.id == first.id
    assert len(catalog.snapshots(game)) == 1


def test_rewritten_but_identical_content_creates_no_snapshot(setup, context, saves):
    catalog, game, engine = setup
    engine.backup(game, context, Trigger.MANUAL)
    touch_later(saves / "slot1.sav", b"level 1")
    assert engine.backup(game, context, Trigger.MANUAL).unchanged


def test_changed_file_creates_snapshot_and_dedupes(setup, context, saves, tmp_path):
    catalog, game, engine = setup
    first = engine.backup(game, context, Trigger.MANUAL).snapshot
    touch_later(saves / "slot1.sav", b"level 2")

    result = engine.backup(game, context, Trigger.MANUAL)
    assert result.changed_files == 1
    files = {f.template: f.digest for f in catalog.snapshot_files(result.snapshot.id)}
    old = {f.template: f.digest for f in catalog.snapshot_files(first.id)}
    assert files["<appdata>/G/profile.dat"] == old["<appdata>/G/profile.dat"]
    assert files["<appdata>/G/slot1.sav"] != old["<appdata>/G/slot1.sav"]
    assert len(list(ObjectStore(tmp_path / "backups").digests())) == 3


def test_deleted_file_creates_snapshot(setup, context, saves):
    catalog, game, engine = setup
    engine.backup(game, context, Trigger.MANUAL)
    (saves / "profile.dat").unlink()
    assert engine.backup(game, context, Trigger.MANUAL).snapshot.file_count == 1


def test_unreadable_file_is_skipped(setup, context, saves, monkeypatch):
    catalog, game, engine = setup
    real_put = engine.store.put_file

    def locked(path):
        if path.name == "slot1.sav":
            raise PermissionError(13, "locked by another process")
        return real_put(path)

    monkeypatch.setattr(engine.store, "put_file", locked)
    result = engine.backup(game, context, Trigger.MANUAL)
    assert result.snapshot.file_count == 1
    assert result.skipped == [
        ("<appdata>/G/slot1.sav", "could not read: locked by another process")
    ]


def test_nothing_to_back_up(setup, context, saves):
    catalog, game, engine = setup
    for f in saves.iterdir():
        f.unlink()
    with pytest.raises(NothingToBackUpError):
        engine.backup(game, context, Trigger.MANUAL)


def test_backup_command(saves):
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", str(saves)])

    first = runner.invoke(app, ["backup", "G"])
    assert first.exit_code == 0, first.output
    assert "Snapshot #1 of G: 2 files" in first.output
    assert "No changes since snapshot #1" in runner.invoke(app, ["backup", "G"]).output


def test_unreadable_file_keeps_previous_version(setup, context, saves, monkeypatch):
    catalog, game, engine = setup
    first = engine.backup(game, context, Trigger.MANUAL).snapshot
    touch_later(saves / "slot1.sav", b"level 2")
    touch_later(saves / "profile.dat", b"more unlocks")
    real_put = engine.store.put_file

    def locked(path):
        if path.name == "slot1.sav":
            raise PermissionError(13, "locked")
        return real_put(path)

    monkeypatch.setattr(engine.store, "put_file", locked)
    result = engine.backup(game, context, Trigger.MANUAL)
    old = {f.template: f.digest for f in catalog.snapshot_files(first.id)}
    new = {f.template: f.digest for f in catalog.snapshot_files(result.snapshot.id)}
    assert new["<appdata>/G/slot1.sav"] == old["<appdata>/G/slot1.sav"]
    assert "kept the previous version" in result.skipped[0][1]
