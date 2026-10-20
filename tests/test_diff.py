import os

from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.diff import Change, diff_files
from saveix.core.models import SnapshotFile

runner = CliRunner()


def f(template, digest, size=1):
    return SnapshotFile(1, "<appdata>/G", template, digest, size, 0)


def test_diff_files():
    old = [f("a", "1"), f("b", "2"), f("c", "3", 10)]
    new = [f("a", "1"), f("c", "4", 20), f("d", "5")]
    changes = diff_files(old, new)
    assert [(c.change, c.template) for c in changes] == [
        (Change.REMOVED, "b"),
        (Change.MODIFIED, "c"),
        (Change.ADDED, "d"),
    ]
    assert (changes[1].old_size, changes[1].new_size) == (10, 20)


def write(path, text, second):
    path.write_text(text)
    os.utime(path, ns=(second * 10**9, second * 10**9))


def test_diff_command(fake_home):
    saves = fake_home / "AppData" / "Roaming" / "G"
    saves.mkdir(parents=True)
    write(saves / "slot1.sav", "a", 1)
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", str(saves)])
    runner.invoke(app, ["backup", "G"])
    write(saves / "slot1.sav", "bb", 2)
    write(saves / "slot2.sav", "c", 2)
    runner.invoke(app, ["backup", "G"])

    result = runner.invoke(app, ["diff", "2"])
    assert result.exit_code == 0, result.output
    assert "#1 -> #2:" in result.output
    assert "~ <appdata>/G/slot1.sav  (1 B -> 2 B)" in result.output
    assert "+ <appdata>/G/slot2.sav" in result.output

    assert "no differences" in runner.invoke(app, ["diff", "1", "1"]).output
    assert runner.invoke(app, ["diff", "1"]).exit_code == 1
