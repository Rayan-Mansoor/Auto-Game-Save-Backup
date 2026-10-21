import os

import pytest

from saveix.core.backup import BackupEngine
from saveix.core.catalog import Catalog
from saveix.core.daemon import Runner
from saveix.core.models import Source, SourceKind, Trigger
from saveix.core.sessions import SessionDetector
from saveix.core.store import ObjectStore
from tests.fakes import FakeClock, FakeProcesses, FakeWatcher, counting_timestamps


@pytest.fixture
def env(tmp_path, fake_home, context):
    saves = fake_home / "AppData" / "Roaming" / "G"
    saves.mkdir(parents=True)
    catalog = Catalog(tmp_path / "c.sqlite3")
    game = catalog.add_game("G")
    catalog.add_source(game, Source(SourceKind.FOLDER, "<appdata>/G"))
    catalog.set_executables(game, ["g.exe"])
    procs, clock = FakeProcesses(), FakeClock()
    stamps = counting_timestamps()
    engine = BackupEngine(catalog, ObjectStore(tmp_path / "b"), clock=stamps, retry_delay=0)
    notices = []
    runner = Runner(
        catalog,
        engine,
        SessionDetector(procs, end_grace_seconds=0, clock=clock),
        clock=stamps,
        notify=notices.append,
        quiet_period=10,
        checkpoint_interval=0,
        watcher_factory=FakeWatcher,
        monotonic=clock,
    )
    runner.test_clock = clock
    yield catalog, game, runner, procs, saves, notices
    catalog.close()


def save(path, data, second):
    path.write_bytes(data)
    os.utime(path, ns=(second * 10**9, second * 10**9))


def played(catalog, game):
    """Snapshots taken during play, leaving out the one from the start of the session."""
    return [s for s in catalog.snapshots(game) if s.trigger is not Trigger.SESSION_START]


def test_snapshot_when_session_ends(env):
    catalog, game, runner, procs, saves, notices = env
    save(saves / "slot.sav", b"before", 1)

    procs.start("g.exe")
    runner.poll()
    save(saves / "slot.sav", b"after playing", 2)
    procs.stop_all()
    runner.poll()

    [session] = catalog.sessions(game)
    assert session.ended_at and not session.crashed
    start, end = catalog.snapshots(game)
    assert start.trigger is Trigger.SESSION_START and end.trigger is Trigger.SESSION_END
    assert {start.session_id, end.session_id} == {session.id}
    before = catalog.snapshot_files(start.id)[0]
    assert engine_read(runner, before.digest) == b"before"
    assert [n.message for n in notices] == [
        "session started",
        f"saved snapshot #{start.id}",
        f"saved snapshot #{end.id}",
        "session ended; 2 snapshots saved",
    ]
    assert [n.important for n in notices] == [False, False, False, True]


def engine_read(runner, digest):
    return runner.engine.store.read_bytes(digest)


def test_session_start_is_not_stored_twice(env):
    catalog, game, runner, procs, saves, notices = env
    save(saves / "slot.sav", b"same", 1)
    for _ in range(2):
        procs.start("g.exe")
        runner.poll()
        procs.stop_all()
        runner.poll()
    # Nothing changed while playing, so only the first session start was stored.
    assert [s.trigger for s in catalog.snapshots(game)] == [Trigger.SESSION_START]


def test_session_without_saves_warns(env):
    catalog, game, runner, procs, saves, notices = env
    procs.start("g.exe")
    runner.poll()
    # A game with no saves yet is not a problem when the session starts...
    assert not any(n.warning for n in notices)
    procs.stop_all()
    runner.poll()
    # ...but still having none when it ends is worth a warning.
    assert any(n.warning and "No save files" in n.message for n in notices)
    assert catalog.sessions(game)[0].ended_at


def test_interrupted_sessions_are_closed_on_start(env, tmp_path):
    catalog, game, runner, procs, saves, notices = env
    procs.start("g.exe")
    runner.poll()
    assert catalog.open_sessions()
    Runner(catalog, runner.engine, runner.detector)
    assert catalog.open_sessions() == []


def test_checkpoints_after_writes_settle(env):
    catalog, game, runner, procs, saves, notices = env
    clock = runner.test_clock
    save(saves / "slot.sav", b"start", 1)
    procs.start("g.exe")
    runner.poll()
    watcher = runner.active[game.id].watcher
    assert watcher.folders == [saves]

    # A burst of writes: nothing until the folder has been quiet for 10 seconds.
    save(saves / "slot.sav", b"checkpoint 1", 2)
    watcher.change(saves / "slot.sav.tmp")
    clock.now = 3
    watcher.change(saves / "slot.sav")
    clock.now = 8
    runner.poll()
    assert played(catalog, game) == []
    clock.now = 14
    runner.poll()
    [first] = played(catalog, game)
    assert first.trigger is Trigger.CHECKPOINT

    # Changes outside the save folder are ignored.
    watcher.change(saves.parent / "Other" / "x")
    clock.now = 100
    runner.poll()
    assert len(played(catalog, game)) == 1

    save(saves / "slot.sav", b"checkpoint 2", 3)
    watcher.change(saves / "slot.sav")
    clock.now = 111
    runner.poll()
    assert [s.trigger for s in played(catalog, game)] == [Trigger.CHECKPOINT] * 2

    procs.stop_all()
    runner.poll()
    assert watcher.stopped
    # The end-of-session snapshot is skipped because nothing changed since the last checkpoint.
    assert len(played(catalog, game)) == 2
    assert all(s.session_id == catalog.sessions(game)[0].id for s in catalog.snapshots(game))


def test_checkpoint_frequency_is_limited(env):
    catalog, game, runner, procs, saves, notices = env
    clock = runner.test_clock
    runner.checkpoint_interval = 600
    save(saves / "slot.sav", b"start", 1)
    procs.start("g.exe")
    runner.poll()
    watcher = runner.active[game.id].watcher

    def autosave(data, at):
        save(saves / "slot.sav", data, int(at))
        clock.now = at
        watcher.change(saves / "slot.sav")
        clock.now = at + 11
        runner.poll()

    autosave(b"1", 0)
    autosave(b"2", 60)
    autosave(b"3", 120)
    assert len(played(catalog, game)) == 1
    # The waiting save is taken once ten minutes have passed since the last checkpoint.
    clock.now = 611
    runner.poll()
    assert len(played(catalog, game)) == 2

    catalog.set_checkpoint_interval(game, 0)
    runner.active[game.id].game.checkpoint_interval_minutes = 0
    autosave(b"4", 700)
    assert len(played(catalog, game)) == 3


def test_config_only_changes_do_not_trigger_checkpoints(env, fake_home):
    from saveix.core.models import SourceRole

    catalog, game, runner, procs, saves, notices = env
    clock = runner.test_clock
    ini = fake_home / "Documents" / "G.ini"
    save(ini, b"volume=1", 1)
    catalog.add_source(game, Source(SourceKind.FILE, "<documents>/G.ini", SourceRole.CONFIG))
    save(saves / "slot.sav", b"start", 1)
    procs.start("g.exe")
    runner.poll()
    watcher = runner.active[game.id].watcher

    save(ini, b"volume=2", 2)
    watcher.change(ini)
    clock.now = 100
    runner.poll()
    assert played(catalog, game) == []

    save(saves / "slot.sav", b"progress", 3)
    watcher.change(saves / "slot.sav")
    clock.now = 200
    runner.poll()
    [snap] = played(catalog, game)
    files = {f.template: f for f in catalog.snapshot_files(snap.id)}
    assert "<documents>/G.ini" in files
