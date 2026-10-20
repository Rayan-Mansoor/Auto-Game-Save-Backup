import pytest
from typer.testing import CliRunner

from saveix.cli import app
from tests import fake_provider

runner = CliRunner()


@pytest.fixture(autouse=True)
def fake_enabled(monkeypatch, fake_home):
    available = lambda: {"fake": lambda: fake_provider.factory}  # noqa: E731
    monkeypatch.setattr("saveix.core.providers.available_providers", available)
    monkeypatch.setattr("saveix.cli.providers.available_providers", available)
    runner.invoke(app, ["providers", "enable", "fake"])


def test_suggest_adds_existing_locations(fake_home):
    saves = fake_home / "AppData/LocalLow/Team Cherry/Hollow Knight"
    saves.mkdir(parents=True)
    (saves / "user1.dat").write_text("progress")
    remote = fake_home / "AppData/Roaming/Goldberg SteamEmu Saves/367520/remote"
    remote.mkdir(parents=True)
    (remote / "cloud.dat").write_text("x")
    runner.invoke(app, ["game", "add", "Hollow Knight"])

    result = runner.invoke(app, ["suggest", "Hollow Knight", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Found Hollow Knight in fake." in result.output
    assert "not on this PC" in result.output or "registry" in result.output

    shown = runner.invoke(app, ["game", "show", "Hollow Knight"]).output
    assert "<locallow>/Team Cherry/Hollow Knight/*.dat  (provider:fake)" in shown
    assert "<appdata>/Goldberg SteamEmu Saves/367520/remote  (provider:fake)" in shown
    assert "Steam app ID 367520" in shown
    assert "executables: hollow_knight.exe" in shown
    assert "synced by a cloud service" in shown
    assert "1 files" in runner.invoke(app, ["scan", "Hollow Knight"]).output.split("\n")[0]


def test_suggest_asks_which_match_and_confirms(fake_home):
    (fake_home / "Documents/The Witcher 3/gamesaves").mkdir(parents=True)
    (fake_home / "Documents/The Witcher 3/gamesaves/a.sav").write_text("x")
    runner.invoke(app, ["game", "add", "W3"])
    result = runner.invoke(app, ["suggest", "W3", "--query", "t"], input="2\nn\n")
    assert "2. The Witcher 3" in result.output
    assert "Found The Witcher 3" in result.output
    assert "(0 sources)" in runner.invoke(app, ["game", "list"]).output


def test_suggest_unknown_game(fake_home):
    runner.invoke(app, ["game", "add", "Zelda"])
    result = runner.invoke(app, ["suggest", "Zelda"])
    assert result.exit_code == 1
    assert "No provider knows Zelda" in result.output
