from datetime import UTC, datetime

from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.models import Snapshot, Trigger
from saveix.core.retention import protected

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
