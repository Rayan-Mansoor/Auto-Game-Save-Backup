import os

import pytest

from saveix.core.backup import BackupEngine
from saveix.core.catalog import Catalog
from saveix.core.daemon import Runner
from saveix.core.models import Source, SourceKind, Trigger
from saveix.core.sessions import SessionDetector
from saveix.core.store import ObjectStore
from tests.fakes import FakeClock, FakeProcesses, counting_timestamps


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
    )
    yield catalog, game, runner, procs, saves, notices
    catalog.close()


def save(path, data, second):
    path.write_bytes(data)
    os.utime(path, ns=(second * 10**9, second * 10**9))


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
    [snap] = catalog.snapshots(game)
    assert snap.trigger is Trigger.SESSION_END and snap.session_id == session.id
    assert [n.message for n in notices] == [
        "session started",
        f"saved snapshot #{snap.id}",
        "session ended",
    ]


def test_session_without_saves_warns(env):
    catalog, game, runner, procs, saves, notices = env
    procs.start("g.exe")
    runner.poll()
    procs.stop_all()
    runner.poll()
    assert any(n.warning and "No save files" in n.message for n in notices)
    assert catalog.sessions(game)[0].ended_at


def test_interrupted_sessions_are_closed_on_start(env, tmp_path):
    catalog, game, runner, procs, saves, notices = env
    procs.start("g.exe")
    runner.poll()
    assert catalog.open_sessions()
    Runner(catalog, runner.engine, runner.detector)
    assert catalog.open_sessions() == []
