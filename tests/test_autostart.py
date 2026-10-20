import sys

import pytest
from typer.testing import CliRunner

from saveix.cli import app
from saveix.core import autostart

runner = CliRunner()


class MemoryRunKey:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, command):
        self.values[name] = command

    def delete(self, name):
        self.values.pop(name, None)


def test_enable_and_disable():
    key = MemoryRunKey()
    assert not autostart.is_enabled(key)
    command = autostart.enable(key)
    assert command.endswith("-m saveix tray") or command.endswith(" tray")
    assert autostart.is_enabled(key)
    autostart.disable(key)
    assert not autostart.is_enabled(key)


@pytest.mark.skipif(sys.platform == "win32", reason="Windows supports autostart")
def test_unavailable_off_windows():
    result = runner.invoke(app, ["autostart", "on"])
    assert result.exit_code == 1
    assert "only supported on Windows" in result.output


def test_cli_with_fake_key(monkeypatch):
    key = MemoryRunKey()
    monkeypatch.setattr(autostart, "_key", lambda run_key: key)
    assert "Does not start" in runner.invoke(app, ["autostart"]).output
    assert runner.invoke(app, ["autostart", "on"]).exit_code == 0
    assert "Starts with Windows." in runner.invoke(app, ["autostart", "status"]).output
    assert runner.invoke(app, ["autostart", "off"]).exit_code == 0
    assert runner.invoke(app, ["autostart", "maybe"]).exit_code == 1
