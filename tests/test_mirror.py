import sqlite3

from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.catalog import Catalog
from saveix.core.mirror import mirror
from saveix.core.store import ObjectStore

runner = CliRunner()


def test_mirror_copies_new_and_removes_collected(tmp_path):
    store = ObjectStore(tmp_path / "backups")
    target = tmp_path / "OneDrive" / "saveix"
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        catalog.add_game("G")
        a, _ = store.put_bytes(b"a")
        b, _ = store.put_bytes(b"b")

        report = mirror(catalog, store, target)
        assert (report.copied, report.removed) == (2, 0)
        assert ObjectStore(target).read_bytes(a) == b"a"

        store.delete(b)
        c, _ = store.put_bytes(b"c")
        report = mirror(catalog, store, target)
        assert (report.copied, report.removed) == (1, 1)
        assert sorted(ObjectStore(target).digests()) == sorted([a, c])

    copy = sqlite3.connect(target / "catalog.sqlite3")
    assert copy.execute("SELECT name FROM games").fetchall() == [("G",)]
    copy.close()


def test_mirror_command(fake_home, tmp_path):
    saves = fake_home / "AppData/Roaming/G"
    saves.mkdir(parents=True)
    (saves / "s.sav").write_text("progress")
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", str(saves)])
    runner.invoke(app, ["backup", "G"])

    assert runner.invoke(app, ["mirror"]).exit_code == 1
    runner.invoke(app, ["config", "set", "mirror_dir", str(tmp_path / "mirror")])
    result = runner.invoke(app, ["mirror"])
    assert result.exit_code == 0, result.output
    assert "Mirror updated: 1 new files" in result.output
    assert (tmp_path / "mirror" / "catalog.sqlite3").exists()
