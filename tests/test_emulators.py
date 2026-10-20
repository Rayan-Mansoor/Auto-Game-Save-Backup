import json

from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.emulators import Emulator, find_remote_folders, load_emulators, translate

runner = CliRunner()


def test_builtin_list_loads():
    names = [e.name for e in load_emulators()]
    assert "Goldberg" in names and "CODEX" in names


def test_user_file_adds_and_overrides(tmp_path):
    user = tmp_path / "emulators.json"
    user.write_text(
        json.dumps(
            {
                "emulators": [
                    {"name": "Goldberg", "remote": "<appdata>/Custom/{appid}", "verified": True},
                    {"name": "Mine", "remote": "<documents>/Mine/{appid}"},
                    {"name": "Broken", "remote": "<documents>/no-appid"},
                ]
            }
        )
    )
    emulators = {e.name: e for e in load_emulators(user)}
    assert emulators["Goldberg"].remote == "<appdata>/Custom/{appid}"
    assert "Mine" in emulators and "Broken" not in emulators


def test_find_and_translate(fake_home, context):
    remote = fake_home / "AppData" / "Roaming" / "Goldberg SteamEmu Saves" / "367520" / "remote"
    remote.mkdir(parents=True)
    emulators = [
        Emulator("Goldberg", "<appdata>/Goldberg SteamEmu Saves/{appid}/remote"),
        Emulator("Other", "<appdata>/Other/{appid}/remote"),
        Emulator("NeedsInstall", "<install>/saves/{appid}"),
    ]
    found = find_remote_folders(367520, context, emulators)
    assert [(m.emulator.name, m.template) for m in found] == [
        ("Goldberg", "<appdata>/Goldberg SteamEmu Saves/367520/remote")
    ]
    translated = translate("<steamremote>/savedata", 367520, context, emulators)
    assert [m.template for m in translated] == [
        "<appdata>/Goldberg SteamEmu Saves/367520/remote/savedata"
    ]
    assert translate("<appdata>/x", 367520, context, emulators) == []


def test_emulators_command(fake_home, tmp_path):
    remote = fake_home / "AppData" / "Roaming" / "Goldberg SteamEmu Saves" / "367520" / "remote"
    remote.mkdir(parents=True)
    (remote / "user1.dat").write_text("x")
    runner.invoke(app, ["game", "add", "HK"])
    assert runner.invoke(app, ["emulators", "HK"]).exit_code == 1

    game_dir = tmp_path / "HK"
    game_dir.mkdir()
    (game_dir / "steam_appid.txt").write_text("367520")
    runner.invoke(app, ["identify", str(game_dir), "--game", "HK"])

    result = runner.invoke(app, ["emulators", "HK", "--add"])
    assert result.exit_code == 0, result.output
    assert "Goldberg: <appdata>/Goldberg SteamEmu Saves/367520/remote" in result.output
    assert "(emulator)" in runner.invoke(app, ["game", "show", "HK"]).output
    assert "already a source" in runner.invoke(app, ["emulators", "HK", "--add"]).output
