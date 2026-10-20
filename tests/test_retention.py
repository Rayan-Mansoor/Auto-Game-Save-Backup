from datetime import UTC, datetime

from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.catalog import Catalog
from saveix.core.models import Snapshot, Trigger
from saveix.core.retention import protected, prune

runner = CliRunner()
NOW = datetime(2026, 6, 1, tzinfo=UTC)


def snap(id, trigger=Trigger.CHECKPOINT, health="ok", day=1, **kwargs):
    return Snapshot(
        id=id,
        game_id=1,
        created_at=f"2026-05-{day:02d}T12:00:00Z",
        trigger=trigger,
        file_count=1,
        total_size=1,
        fingerprint=str(id),
        health=health,
        **kwargs,
    )


def test_latest_and_newest_healthy_are_protected():
    snaps = [snap(1), snap(2), snap(3)]
    assert protected(snaps, NOW) == {3: "latest"}


def test_pinned_labeled_and_recent_safety():
    snaps = [
        snap(1, pinned=True),
        snap(2, label="Before boss"),
        snap(3, Trigger.SAFETY, day=1),
        snap(4, Trigger.SAFETY, day=20),
        snap(5),
    ]
    assert protected(snaps, NOW) == {
        1: "pinned",
        2: "labeled",
        4: "recent safety snapshot",
        5: "latest",
    }


def test_last_healthy_before_damage():
    snaps = [snap(1), snap(2), snap(3, health="suspicious"), snap(4), snap(5, health="suspicious")]
    assert protected(snaps, NOW) == {
        2: "last healthy before #3",
        4: "last healthy before #5",
        5: "latest",
    }


def test_pin_commands(fake_home):
    saves = fake_home / "AppData" / "Roaming" / "G"
    saves.mkdir(parents=True)
    (saves / "s").write_text("x")
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", str(saves)])
    runner.invoke(app, ["backup", "G"])
    assert runner.invoke(app, ["pin", "1"]).exit_code == 0
    assert "(pinned)" in runner.invoke(app, ["timeline", "G"]).output
    assert runner.invoke(app, ["unpin", "1"]).exit_code == 0
    assert "(pinned)" not in runner.invoke(app, ["timeline", "G"]).output
    assert runner.invoke(app, ["pin", "9"]).exit_code == 1


# Session thinning ---------------------------------------------------------------


def play(catalog, game, sessions, checkpoints, start_day=1, suspicious_end=()):
    """Record sessions of checkpoints followed by an end-of-session snapshot."""
    day = start_day
    for n in range(sessions):
        session = catalog.start_session(game, f"2026-05-{day:02d}T10:00:00Z")
        for c in range(checkpoints):
            snapshot = catalog.add_snapshot(
                game,
                Trigger.CHECKPOINT,
                f"2026-05-{day:02d}T10:{c + 1:02d}:00Z",
                f"{n}-{c}",
                [],
                session.id,
            )
            catalog.set_health(snapshot.id, "ok", [])
        end = catalog.add_snapshot(
            game, Trigger.SESSION_END, f"2026-05-{day:02d}T12:00:00Z", f"{n}-end", [], session.id
        )
        catalog.set_health(end.id, "suspicious" if n in suspicious_end else "ok", [])
        catalog.end_session(session.id, f"2026-05-{day:02d}T12:00:00Z")
        day += 1


def kept_triggers(catalog, game):
    by_session = {}
    for s in catalog.snapshots(game):
        by_session.setdefault(s.session_id, []).append(s.trigger)
    return by_session


def test_older_sessions_keep_only_their_final_state(tmp_path):
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("G")
        play(catalog, game, sessions=5, checkpoints=4)
        removed = prune(catalog, game, NOW, recent_sessions=3)

        assert len(removed) == 2 * 4
        kept = kept_triggers(catalog, game)
        assert kept[1] == kept[2] == [Trigger.SESSION_END]
        assert kept[3] == kept[4] == kept[5] == [Trigger.CHECKPOINT] * 4 + [Trigger.SESSION_END]
        assert prune(catalog, game, NOW, recent_sessions=3) == []


def test_damaged_final_state_keeps_last_healthy_checkpoint(tmp_path):
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("G")
        play(catalog, game, sessions=4, checkpoints=3, suspicious_end={0})
        prune(catalog, game, NOW, recent_sessions=3)
        assert kept_triggers(catalog, game)[1] == [Trigger.CHECKPOINT, Trigger.SESSION_END]


def test_labeled_checkpoints_survive_and_dry_run_changes_nothing(tmp_path):
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("G")
        play(catalog, game, sessions=4, checkpoints=3)
        catalog.set_label(1, "Act 1 done")
        assert len(prune(catalog, game, NOW, 3, dry_run=True)) == 2
        assert len(catalog.snapshots(game)) == 16
        prune(catalog, game, NOW, 3)
        assert [s.id for s in catalog.snapshots(game)][:2] == [1, 4]


def test_prune_command_respects_keep_all(fake_home):
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["config", "set", "keep_all_snapshots", "true"])
    assert "nothing is ever removed" in runner.invoke(app, ["prune"]).output
    runner.invoke(app, ["config", "set", "keep_all_snapshots", "false"])
    assert "Removed 0 snapshots." in runner.invoke(app, ["prune"]).output


def test_long_history_stays_small_and_useful(tmp_path):
    """50 sessions with frequent autosaves, played on dozens of days over several months."""
    from datetime import timedelta

    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("G")
        start = datetime(2026, 1, 1, 18, tzinfo=UTC)
        day = start
        for n in range(50):
            if n % 10 not in (3, 7):  # some evenings have two sessions
                day += timedelta(days=1 + (n % 4) * 2)
            session = catalog.start_session(game, day.isoformat())
            for c in range(12):
                at = (day + timedelta(minutes=10 * c + n % 2 * 300)).isoformat()
                snapshot = catalog.add_snapshot(
                    game, Trigger.CHECKPOINT, at, f"{n}-{c}", [], session.id
                )
                catalog.set_health(snapshot.id, "ok", [])
            catalog.end_session(session.id, at)
        total = len(catalog.snapshots(game))
        play_days = {s.created_at[:10] for s in catalog.snapshots(game)}

        prune(catalog, game, day, recent_sessions=3, tz=UTC)
        kept = catalog.snapshots(game)
        sessions = catalog.sessions(game)

        assert total == 600 and len(play_days) > 30
        # Every checkpoint of the last three sessions is kept.
        for session in sessions[-3:]:
            assert sum(s.session_id == session.id for s in kept) == 12
        # One snapshot per play-day for the most recent 30 play-days, one per week before.
        older = [s for s in kept if s.session_id not in {x.id for x in sessions[-3:]}]
        days = [s.created_at[:10] for s in older]
        assert len(days) == len(set(days))
        assert 40 <= len(kept) <= 80

        # Months without playing remove nothing more.
        assert prune(catalog, game, day + timedelta(days=365), 3, tz=UTC) == []


def test_count_limit_removes_oldest_unprotected(tmp_path):
    from saveix.core.config import Settings
    from saveix.core.retention import apply_policy

    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("G")
        for i in range(6):
            s = catalog.add_snapshot(game, Trigger.MANUAL, f"2026-05-01T10:0{i}:00Z", str(i), [])
            catalog.set_health(s.id, "ok", [])
        catalog.set_pinned(1, True)
        settings = Settings(max_snapshots_per_game=3)

        report = apply_policy(catalog, game, settings, NOW)
        assert [r.snapshot.id for r in report.removals] == [2, 3, 4]
        assert [s.id for s in catalog.snapshots(game)] == [1, 5, 6]
        assert report.warnings == []

        report = apply_policy(catalog, game, Settings(max_snapshots_per_game=1), NOW)
        assert [r.snapshot.id for r in report.removals] == [5]
        assert "because the rest are protected" in report.warnings[0]


def test_storage_limit(tmp_path):
    import os

    from saveix.core.config import Settings
    from saveix.core.models import SnapshotFile
    from saveix.core.retention import apply_storage_limit
    from saveix.core.store import ObjectStore

    store = ObjectStore(tmp_path / "b")
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("G")
        shared, _ = store.put_bytes(b"same in every snapshot")
        for i in range(4):
            unique, _ = store.put_bytes(os.urandom(400 * 1024))
            files = [
                SnapshotFile(None, "<appdata>/G", "<appdata>/G/a", shared, 1, 0),
                SnapshotFile(None, "<appdata>/G", "<appdata>/G/b", unique, 1, 0),
            ]
            s = catalog.add_snapshot(
                game, Trigger.MANUAL, f"2026-05-0{i + 1}T00:00:00Z", str(i), files
            )
            catalog.set_health(s.id, "ok", [])

        report = apply_storage_limit(catalog, store, Settings(max_storage_mb=1), NOW)
        assert [r.snapshot.id for r in report.removals] == [1, 2]
        assert report.warnings == []

        assert apply_storage_limit(catalog, store, Settings(), NOW).removals == []

        catalog.set_pinned(3, True)
        for i in range(2):
            unique, _ = store.put_bytes(os.urandom(400 * 1024))
            files = [SnapshotFile(None, "<appdata>/G", "<appdata>/G/b", unique, 1, 0)]
            catalog.add_snapshot(game, Trigger.MANUAL, f"2026-05-1{i}T00:00:00Z", f"x{i}", files)
        report = apply_storage_limit(catalog, store, Settings(max_storage_mb=1), NOW)
        # #4 stays because it is the newest healthy snapshot.
        assert [r.snapshot.id for r in report.removals] == [5]
        assert "remaining snapshots are protected" in report.warnings[0]
