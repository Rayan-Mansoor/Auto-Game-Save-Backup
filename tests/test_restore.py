import hashlib
import itertools
import os

import pytest
from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.backup import BackupEngine
from saveix.core.catalog import Catalog
from saveix.core.models import Source, SourceKind, Trigger
from saveix.core.restore import Action, Restorer
from saveix.core.store import CorruptObjectError, ObjectStore

runner = CliRunner()


def write(path, data, second):
    path.write_bytes(data)
    os.utime(path, ns=(second * 10**9, second * 10**9))


@pytest.fixture
def saves(fake_home):
    root = fake_home / "AppData" / "Roaming" / "G"
    root.mkdir(parents=True)
    return root


@pytest.fixture
def env(tmp_path, saves, context):
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    game = catalog.add_game("G")
    catalog.add_source(game, Source(SourceKind.FOLDER, "<appdata>/G"))
    store = ObjectStore(tmp_path / "backups")
    counter = itertools.count(1)
    engine = BackupEngine(catalog, store, clock=lambda: f"t{next(counter)}", retry_delay=0)
    restorer = Restorer(catalog, store, engine)

    def snap(**files):
        for name, (data, second) in files.items():
            write(saves / name, data, second)
        return engine.backup(game, context, Trigger.MANUAL).snapshot

    yield catalog, game, restorer, snap
    catalog.close()


def digests(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}


def test_restore_older_stage_and_go_forward_again(env, saves, context):
    catalog, game, restorer, snap = env
    first = snap(**{"slot.sav": (b"stage 1", 1)})
    first_state = digests(saves)
    snap(**{"slot.sav": (b"stage 2", 2)})
    third = snap(**{"slot.sav": (b"stage 3", 3), "slot2.sav": (b"new slot", 3)})
    third_state = digests(saves)

    result = restorer.execute(restorer.plan(game, first, context), context)
    assert digests(saves) == first_state
    assert (result.written, result.deleted) == (1, 1)
    assert (saves / "slot.sav").stat().st_mtime_ns == 1 * 10**9
    # The state before restoring was already snapshot #3, so no extra safety copy was needed.
    assert result.safety_snapshot.id == third.id
    assert [s.id for s in catalog.snapshots(game)] == [1, 2, 3]

    restorer.execute(restorer.plan(game, third, context), context)
    assert digests(saves) == third_state


def test_unsaved_progress_gets_a_safety_snapshot(env, saves, context):
    catalog, game, restorer, snap = env
    first = snap(**{"slot.sav": (b"stage 1", 1)})
    write(saves / "slot.sav", b"unsaved newer progress", 5)

    result = restorer.execute(restorer.plan(game, first, context), context)
    assert result.safety_snapshot.trigger is Trigger.SAFETY
    files = catalog.snapshot_files(result.safety_snapshot.id)
    assert files[0].digest == hashlib.sha256(b"unsaved newer progress").hexdigest()


def test_keep_extra_files(env, saves, context):
    catalog, game, restorer, snap = env
    first = snap(**{"slot.sav": (b"1", 1)})
    snap(**{"extra.sav": (b"2", 2)})
    plan = restorer.plan(game, first, context, remove_extra=False)
    assert plan.of(Action.DELETE) == []
    assert not plan.has_changes


def test_matching_files_are_kept(env, saves, context):
    catalog, game, restorer, snap = env
    first = snap(**{"a.sav": (b"1", 1), "b.sav": (b"1", 1)})
    write(saves / "b.sav", b"2", 2)
    plan = restorer.plan(game, first, context)
    assert [(f.action, f.path.name) for f in plan.files] == [
        (Action.KEEP, "a.sav"),
        (Action.WRITE, "b.sav"),
    ]


def test_deleted_save_folder_is_recreated(env, saves, context):
    catalog, game, restorer, snap = env
    first = snap(**{"slot.sav": (b"1", 1)})
    (saves / "slot.sav").unlink()
    saves.rmdir()
    restorer.execute(restorer.plan(game, first, context), context)
    assert (saves / "slot.sav").read_bytes() == b"1"


def test_damaged_backup_changes_nothing(env, saves, context):
    catalog, game, restorer, snap = env
    first = snap(**{"slot.sav": (b"stage 1", 1)})
    write(saves / "slot.sav", b"current", 2)
    entry = catalog.snapshot_files(first.id)[0]
    restorer.store.path_for(entry.digest).write_bytes(b"garbage")

    with pytest.raises(CorruptObjectError):
        restorer.execute(restorer.plan(game, first, context), context)
    assert (saves / "slot.sav").read_bytes() == b"current"


def test_restore_command(saves):
    write(saves / "slot.sav", b"stage 1", 1)
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", str(saves)])
    runner.invoke(app, ["backup", "G"])
    write(saves / "slot.sav", b"stage 2", 2)
    runner.invoke(app, ["backup", "G"])

    preview = runner.invoke(app, ["restore", "G", "-s", "1", "--dry-run"])
    assert "write  <appdata>/G/slot.sav" in preview.output
    assert (saves / "slot.sav").read_bytes() == b"stage 2"

    result = runner.invoke(app, ["restore", "G", "-s", "1", "--yes"])
    assert result.exit_code == 0, result.output
    assert (saves / "slot.sav").read_bytes() == b"stage 1"
    assert "Current saves kept as snapshot #2." in result.output
    assert "already match" in runner.invoke(app, ["restore", "G", "-s", "1"]).output


def test_restore_single_source(env, saves, context, fake_home):
    catalog, game, restorer, snap = env
    cfg = fake_home / "Documents" / "G.ini"
    write(cfg, b"cfg 1", 1)
    config_source = catalog.add_source(game, Source(SourceKind.FILE, "<documents>/G.ini"))
    first = snap(**{"slot.sav": (b"1", 1)})
    write(cfg, b"cfg 2", 2)
    snap(**{"slot.sav": (b"2", 2), "extra.sav": (b"x", 2)})

    plan = restorer.plan(game, first, context, only_sources={config_source.id})
    assert [(f.action, f.template) for f in plan.files] == [(Action.WRITE, "<documents>/G.ini")]
    restorer.execute(plan, context)
    assert cfg.read_bytes() == b"cfg 1"
    assert (saves / "slot.sav").read_bytes() == b"2"
    assert (saves / "extra.sav").exists()


def test_restore_unknown_source(env, context):
    from saveix.core.catalog import CatalogError

    catalog, game, restorer, snap = env
    first = snap(**{"slot.sav": (b"1", 1)})
    with pytest.raises(CatalogError):
        restorer.plan(game, first, context, only_sources={99})


def test_restore_refused_while_game_runs(saves, monkeypatch):
    write(saves / "slot.sav", b"stage 1", 1)
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", str(saves)])
    runner.invoke(app, ["backup", "G"])
    write(saves / "slot.sav", b"stage 2", 2)
    monkeypatch.setattr("saveix.cli.restore.running_games", lambda games: games)

    result = runner.invoke(app, ["restore", "G", "--yes"])
    assert result.exit_code == 1
    assert "is running" in result.output
    assert (saves / "slot.sav").read_bytes() == b"stage 2"


def test_restore_warns_about_cloud_sync(saves):
    write(saves / "slot.sav", b"stage 1", 1)
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", str(saves)])
    runner.invoke(app, ["backup", "G"])
    write(saves / "slot.sav", b"stage 2", 2)
    assert runner.invoke(app, ["game", "set-cloud", "G", "true"]).exit_code == 0
    assert "also synced by a cloud service" in runner.invoke(app, ["game", "show", "G"]).output

    result = runner.invoke(app, ["restore", "G", "--yes"])
    assert result.exit_code == 0
    assert "choose the local files" in result.output

    runner.invoke(app, ["game", "set-cloud", "G", "false"])
    write(saves / "slot.sav", b"stage 3", 3)
    assert "cloud" not in runner.invoke(app, ["restore", "G", "--yes"]).output
