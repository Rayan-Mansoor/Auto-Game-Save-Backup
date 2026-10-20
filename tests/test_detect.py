import threading
import time

from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.detect import ChangeRecorder, is_noise, suggest

runner = CliRunner()


def test_noise_is_ignored():
    assert is_noise("<localappdata>/G/Logs/out.txt")
    assert is_noise("<localappdata>/G/game.log")
    assert is_noise("<localappdata>/NVIDIA/DXCache/x.bin")
    assert is_noise("<appdata>/Microsoft/Windows/Recent/x.lnk")
    assert not is_noise("<locallow>/Team Cherry/Hollow Knight/user1.dat")


def test_suggestions_group_by_game_folder(fake_home, context):
    home = fake_home
    changed = [
        home / "AppData/LocalLow/Team Cherry/Hollow Knight/user1.dat",
        home / "AppData/LocalLow/Team Cherry/Hollow Knight/user1.dat.bak1",
        home / "AppData/LocalLow/Team Cherry/Hollow Knight/shaders/cache.bin",
        home / "Documents/My Games/Hollow Knight/settings.ini",
        home / "AppData/Local/Hollow Knight/Logs/output.log",
        home / "AppData/Roaming/Discord/Cache/data_1",
        home / "AppData/Local/Temp/x.tmp",
    ]
    suggestions = suggest([str(p) for p in changed], context, "Hollow Knight")
    assert [s.template for s in suggestions] == [
        "<locallow>/Team Cherry/Hollow Knight",
        "<documents>/My Games/Hollow Knight",
    ]
    assert len(suggestions[0].files) == 3


def test_suggestion_narrows_to_common_save_folder(fake_home, context):
    base = fake_home / "AppData/Roaming/Studio/SaveGames"
    changed = [base / "slot1.sav", base / "slot1.sav.backup"]
    [s] = suggest([str(p) for p in changed], context, "Unrelated Name")
    assert s.template == "<appdata>/Studio/SaveGames"


def test_install_folder_saves(fake_home, tmp_path):
    from pathlib import Path

    from saveix.core.paths import PathContext

    install = tmp_path / "Games" / "Story"
    context = PathContext.for_system(install=install)
    [s] = suggest([str(install / "SaveData" / "save0.dat")], context, "Story")
    assert s.template == "<install>/SaveData"
    assert Path(context.expand(s.template)) == install / "SaveData"


def test_recorder_ignores_own_folders(tmp_path):
    recorder = ChangeRecorder(ignore=[tmp_path / "saveix"])
    recorder(str(tmp_path / "saveix" / "catalog.sqlite3"))
    recorder(str(tmp_path / "game" / "save.dat"))
    recorder(str(tmp_path))
    assert recorder.paths() == [str(tmp_path / "game" / "save.dat").replace("\\", "/")]


def test_detect_command(fake_home):
    runner.invoke(app, ["game", "add", "Hollow Knight"])
    saves = fake_home / "AppData/LocalLow/Team Cherry/Hollow Knight"
    saves.mkdir(parents=True)

    def play():
        time.sleep(1)
        (saves / "user1.dat").write_text("progress")

    threading.Thread(target=play).start()
    result = runner.invoke(app, ["detect", "Hollow Knight", "--seconds", "3", "--yes"])
    assert result.exit_code == 0, result.output
    assert "<locallow>/Team Cherry/Hollow Knight" in result.output
    shown = runner.invoke(app, ["game", "show", "Hollow Knight"]).output
    assert "<locallow>/Team Cherry/Hollow Knight  (detected)" in shown
