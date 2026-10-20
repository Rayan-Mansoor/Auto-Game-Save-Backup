from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.identify import identify

runner = CliRunner()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_steam_appid_txt(tmp_path):
    write(tmp_path / "Game" / "Binaries" / "steam_appid.txt", "367520\n")
    result = identify(tmp_path / "Game")
    assert result.steam_app_id == 367520
    assert result.evidence == [tmp_path / "Game" / "Binaries" / "steam_appid.txt"]


def test_emulator_ini(tmp_path):
    write(tmp_path / "steam_emu.ini", "[Settings]\n; comment\nAppId = 292030\nUserName=Player\n")
    assert identify(tmp_path).steam_app_id == 292030


def test_gog_info_gives_id_and_name(tmp_path):
    write(tmp_path / "goggame-1308320804.info", '{"gameId": "1308320804", "name": "Hollow Knight"}')
    result = identify(tmp_path)
    assert (result.gog_id, result.name, result.steam_app_id) == (1308320804, "Hollow Knight", None)


def test_ignores_bad_values_and_deep_or_redist_folders(tmp_path):
    write(tmp_path / "steam_appid.txt", "not a number")
    write(tmp_path / "_CommonRedist" / "steam_appid.txt", "1")
    write(tmp_path / "a" / "b" / "c" / "d" / "e" / "steam_appid.txt", "2")
    assert not identify(tmp_path).found


def test_identify_command_stores_ids(fake_home, tmp_path):
    game_dir = tmp_path / "Hollow Knight"
    write(game_dir / "steam_appid.txt", "367520")
    runner.invoke(app, ["game", "add", "HK"])

    result = runner.invoke(app, ["identify", str(game_dir), "--game", "HK"])
    assert result.exit_code == 0, result.output
    assert "Steam app ID: 367520" in result.output
    shown = runner.invoke(app, ["game", "show", "HK"]).output
    assert "Steam app ID 367520" in shown
    assert f"installed in {game_dir}" in shown

    assert runner.invoke(app, ["identify", str(tmp_path / "missing")]).exit_code == 1
