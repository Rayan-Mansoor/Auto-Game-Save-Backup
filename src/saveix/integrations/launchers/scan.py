"""Find installed games from launcher data on this PC."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from saveix.integrations.launchers import vdf


@dataclass(frozen=True)
class InstalledGame:
    store: str
    id: str
    name: str
    install_dir: str
    executable: str | None = None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def default_steam_root() -> Path | None:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                return Path(winreg.QueryValueEx(key, "SteamPath")[0])
        except OSError:
            pass
        fallback = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Steam"
        return fallback if fallback.is_dir() else None
    return None


def steam_games(root: Path | None) -> list[InstalledGame]:
    if root is None or not root.is_dir():
        return []
    libraries = [root]
    folders = vdf.parse(_read(root / "steamapps" / "libraryfolders.vdf")).get("libraryfolders", {})
    for entry in folders.values():
        if isinstance(entry, dict) and entry.get("path"):
            libraries.append(Path(entry["path"]))
    games = []
    for library in dict.fromkeys(libraries):
        for manifest in sorted((library / "steamapps").glob("appmanifest_*.acf")):
            state = vdf.parse(_read(manifest)).get("AppState", {})
            if state.get("appid") and state.get("installdir"):
                folder = library / "steamapps" / "common" / state["installdir"]
                games.append(
                    InstalledGame("steam", state["appid"], state.get("name", ""), str(folder))
                )
    return games


def default_epic_manifests() -> Path:
    program_data = os.environ.get("PROGRAMDATA", "C:/ProgramData")
    return Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"


def epic_games(folder: Path) -> list[InstalledGame]:
    games = []
    for item in sorted(folder.glob("*.item")) if folder.is_dir() else []:
        try:
            data = json.loads(_read(item))
        except json.JSONDecodeError:
            continue
        if data.get("InstallLocation") and data.get("DisplayName"):
            games.append(
                InstalledGame(
                    "epic",
                    str(data.get("AppName", "")),
                    data["DisplayName"],
                    data["InstallLocation"],
                    Path(data.get("LaunchExecutable", "")).name or None,
                )
            )
    return games


def windows_gog_entries() -> Iterable[dict]:
    if sys.platform != "win32":
        return []
    import winreg

    entries = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games")
    except OSError:
        return []
    with root:
        index = 0
        while True:
            try:
                game_id = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            try:
                with winreg.OpenKey(root, game_id) as key:
                    values = {}
                    for name in ("gameName", "path", "exe"):
                        try:
                            values[name] = winreg.QueryValueEx(key, name)[0]
                        except OSError:
                            pass
                    entries.append({"id": game_id, **values})
            except OSError:
                continue
    return entries


def gog_games(entries: Callable[[], Iterable[dict]]) -> list[InstalledGame]:
    games = []
    for entry in entries():
        if entry.get("path") and entry.get("gameName"):
            exe = Path(entry["exe"]).name if entry.get("exe") else None
            games.append(
                InstalledGame("gog", str(entry["id"]), entry["gameName"], entry["path"], exe)
            )
    return games
