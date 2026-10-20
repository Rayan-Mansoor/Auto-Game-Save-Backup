import os

from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.catalog import Catalog
from saveix.core.models import Trigger
from saveix.core.timeline import timeline

runner = CliRunner()


def make_game_with_snapshots(saves, count):
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", str(saves)])
    for i in range(count):
        save = saves / "slot.sav"
        save.write_text(f"progress {i}")
        os.utime(save, ns=(i * 10**9, i * 10**9))
        assert runner.invoke(app, ["backup", "G"]).exit_code == 0


def test_timeline_is_newest_first_with_auto_labels(fake_home, tmp_path):
    saves = fake_home / "AppData" / "Roaming" / "G"
    saves.mkdir(parents=True)
    make_game_with_snapshots(saves, 3)

    result = runner.invoke(app, ["timeline", "G"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert [line.split()[0] for line in lines] == ["#3", "#2", "#1"]
    assert all("Manual backup" in line for line in lines)

    assert len(runner.invoke(app, ["timeline", "G", "-n", "1"]).output.splitlines()) == 1


def test_timeline_prefers_custom_labels(tmp_path):
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("G")
        snap = catalog.add_snapshot(game, Trigger.CHECKPOINT, "2026-01-01T00:00:00Z", "f", [])
        catalog.db.execute("UPDATE snapshots SET label = 'Act 2' WHERE id = ?", (snap.id,))
        catalog.add_snapshot(game, Trigger.SESSION_END, "2026-01-01T01:00:00Z", "g", [])

        entries = timeline(catalog, game)
    assert [(e.label, e.custom_label) for e in entries] == [
        ("End of session", False),
        ("Act 2", True),
    ]


def test_empty_timeline(fake_home):
    runner.invoke(app, ["game", "add", "G"])
    assert "no snapshots yet" in runner.invoke(app, ["timeline", "G"]).output
