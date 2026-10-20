import threading
import time

from saveix.core.models import Game, Source, SourceKind
from saveix.core.watcher import (
    ChangeTracker,
    WatchdogWatcher,
    source_covers,
    watch_game,
    watch_root,
)


def test_watch_root(fake_home, context):
    saves = fake_home / "AppData" / "Roaming" / "G"
    saves.mkdir(parents=True)
    folder = Source(SourceKind.FOLDER, "<appdata>/G")
    glob = Source(SourceKind.GLOB, "<appdata>/G/*/slot*.sav")
    file = Source(SourceKind.FILE, "<appdata>/G/settings.ini")
    missing = Source(SourceKind.FOLDER, "<appdata>/G/not/yet")
    assert watch_root(folder, context) == saves
    assert watch_root(glob, context) == saves
    assert watch_root(file, context) == saves
    assert watch_root(missing, context) == saves
    assert watch_root(Source(SourceKind.REGISTRY, "HKCU/Software/G"), context) is None


def test_source_covers(fake_home, context):
    base = str(fake_home / "AppData" / "Roaming" / "G")
    folder = Source(SourceKind.FOLDER, "<appdata>/G", exclude=["*.log"])
    assert source_covers(folder, context, base + "/sub/slot.sav")
    assert not source_covers(folder, context, base + "/game.log")
    assert not source_covers(folder, context, base + "Other/slot.sav")

    glob = Source(SourceKind.GLOB, "<appdata>/G/*.sav")
    assert source_covers(glob, context, base + "/a.sav")
    assert not source_covers(glob, context, base + "/a.png")

    file = Source(SourceKind.FILE, "<appdata>/G/settings.ini")
    assert source_covers(file, context, base + "/settings.ini")
    assert not source_covers(file, context, base + "/settings.ini.bak")


def test_tracker_waits_for_quiet(fake_home, context):
    game = Game("G", sources=[Source(SourceKind.FOLDER, "<appdata>/G")])
    tracker = ChangeTracker(game, context, quiet_period=5)
    path = str(fake_home / "AppData" / "Roaming" / "G" / "s")
    assert not tracker.record(str(fake_home / "elsewhere"), 0)
    assert tracker.record(path, 0)
    assert not tracker.due(4) and tracker.due(5)
    tracker.reset()
    assert not tracker.pending()


def test_real_watcher_sees_writes(fake_home, context):
    saves = fake_home / "AppData" / "Roaming" / "G"
    saves.mkdir(parents=True)
    game = Game("G", sources=[Source(SourceKind.FOLDER, "<appdata>/G")])
    tracker = ChangeTracker(game, context, quiet_period=0)
    seen = threading.Event()
    original = tracker.record

    def record(path, now):
        if original(path, now):
            seen.set()
        return True

    tracker.record = record
    watcher = WatchdogWatcher()
    try:
        watch_game(game, context, tracker, watcher, time.monotonic)
        time.sleep(0.5)
        (saves / "slot.sav").write_text("progress")
        assert seen.wait(10)
    finally:
        watcher.stop()
