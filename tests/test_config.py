import pytest
from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.config import AppDirs, Config, Settings

runner = CliRunner()


def test_defaults_without_config_file(saveix_home):
    config = Config()

    assert config.settings == Settings()
    assert config.backup_root == saveix_home / "data" / "backups"


def test_settings_round_trip(saveix_home):
    config = Config()
    config.settings.set("checkpoint_interval_minutes", "5")
    config.settings.set("providers", "ludusavi, other")
    config.settings.set("backup_root", str(saveix_home / "elsewhere"))
    config.save()

    reloaded = Config(AppDirs.default())
    assert reloaded.settings.checkpoint_interval_minutes == 5
    assert reloaded.settings.providers == ["ludusavi", "other"]
    assert reloaded.backup_root == saveix_home / "elsewhere"


def test_unknown_keys_in_file_are_ignored(saveix_home):
    saveix_home.mkdir()
    (saveix_home / "config.toml").write_text("future_setting = 1\nrecent_sessions_kept = 7\n")

    assert Config().settings.recent_sessions_kept == 7


def test_set_rejects_bad_values():
    settings = Settings()
    with pytest.raises(KeyError):
        settings.set("nope", "1")
    with pytest.raises(ValueError):
        settings.set("quiet_period_seconds", "-1")


def test_config_cli_set_and_show():
    result = runner.invoke(app, ["config", "set", "quiet_period_seconds", "20"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["config", "show"])
    assert "quiet_period_seconds = 20" in result.output


def test_config_cli_unknown_key():
    result = runner.invoke(app, ["config", "set", "nope", "1"])
    assert result.exit_code == 1
