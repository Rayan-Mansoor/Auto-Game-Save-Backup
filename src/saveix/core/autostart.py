"""Start the tray app when the user logs in to Windows.

Uses the per-user ``Run`` registry key, so no admin rights are needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "saveix"


class RunKey(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, command: str) -> None: ...

    def delete(self, name: str) -> None: ...


class WindowsRunKey:
    def get(self, name: str) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return winreg.QueryValueEx(key, name)[0]
        except OSError:
            return None

    def set(self, name: str, command: str) -> None:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)

    def delete(self, name: str) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except OSError:
            pass


class AutostartUnavailableError(Exception):
    pass


def tray_command() -> str:
    """The command that starts the tray app without a console window."""
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        # The installed app ships a separate windowless tray program next to the CLI.
        tray = executable.with_name("saveix-tray.exe")
        return f'"{tray}"' if tray.exists() else f'"{executable}" tray'
    windowless = executable.with_name("pythonw.exe")
    python = windowless if windowless.exists() else executable
    return f'"{python}" -m saveix tray'


def _key(run_key: RunKey | None) -> RunKey:
    if run_key is not None:
        return run_key
    if sys.platform != "win32":
        raise AutostartUnavailableError("starting with the system is only supported on Windows")
    return WindowsRunKey()


def is_enabled(run_key: RunKey | None = None) -> bool:
    return _key(run_key).get(VALUE_NAME) is not None


def enable(run_key: RunKey | None = None, command: str | None = None) -> str:
    command = command or tray_command()
    _key(run_key).set(VALUE_NAME, command)
    return command


def disable(run_key: RunKey | None = None) -> None:
    _key(run_key).delete(VALUE_NAME)
