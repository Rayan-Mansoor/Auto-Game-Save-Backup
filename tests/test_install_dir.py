from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.catalog import Catalog
from saveix.core.context import context_for

runner = CliRunner()


def test_install_folder_resolves_install_paths(fake_home, tmp_path):
    install = tmp_path / "Games" / "Cracked Story Game"
    (install / "SaveData").mkdir(parents=True)
    (install / "SaveData" / "slot1.sav").write_text("x")
    runner.invoke(app, ["game", "add", "Story"])

    # Without an install folder, the path cannot be turned into <install>/...
    assert runner.invoke(app, ["source", "add", "Story", "<install>/SaveData"]).exit_code == 1

    result = runner.invoke(app, ["game", "set-install", "Story", str(install)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["source", "add", "Story", str(install / "SaveData")])
    assert result.exit_code == 0, result.output

    shown = runner.invoke(app, ["game", "show", "Story"]).output
    assert f"installed in {install}" in shown
    assert "folder   save   <install>/SaveData" in shown
    assert "1 files" in runner.invoke(app, ["scan", "Story"]).output
    assert runner.invoke(app, ["backup", "Story"]).exit_code == 0


def test_moved_install_folder_still_restores(fake_home, tmp_path, saveix_home):
    old = tmp_path / "C" / "Game"
    new = tmp_path / "D" / "Game"
    (old / "saves").mkdir(parents=True)
    (old / "saves" / "s.sav").write_text("progress")
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["game", "set-install", "G", str(old)])
    runner.invoke(app, ["source", "add", "G", str(old / "saves")])
    runner.invoke(app, ["backup", "G"])

    new.mkdir(parents=True)
    runner.invoke(app, ["game", "set-install", "G", str(new)])
    result = runner.invoke(app, ["restore", "G", "--yes"])
    assert result.exit_code == 0, result.output
    assert (new / "saves" / "s.sav").read_text() == "progress"


def test_set_install_rejects_missing_folder_and_clears(fake_home, tmp_path, saveix_home):
    runner.invoke(app, ["game", "add", "G"])
    assert runner.invoke(app, ["game", "set-install", "G", str(tmp_path / "nope")]).exit_code == 1
    runner.invoke(app, ["game", "set-install", "G", str(tmp_path)])
    runner.invoke(app, ["game", "set-install", "G"])
    with Catalog(saveix_home / "data" / "catalog.sqlite3") as catalog:
        game = catalog.get_game("G")
        assert game.install_dir is None
        assert context_for(game).install is None
