"""Work out which game an install folder holds from files shipped with it.

Steam builds and Steam emulators usually carry the game's Steam app ID in
``steam_appid.txt`` or an emulator settings file; GOG builds carry a
``goggame-<id>.info`` file. These IDs let providers suggest save locations and let
saveix translate Steam save paths to emulator save folders.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_DEPTH = 3
"""How many folder levels below the install folder to look."""

SKIP_DIRS = {"__pycache__", "redist", "_commonredist", "directx", "dotnet", "vcredist"}

INI_FILES = {
    "steam_emu.ini",
    "smartsteamemu.ini",
    "coldclientloader.ini",
    "cream_api.ini",
    "steam_api.ini",
    "configs.app.ini",
}
"""Emulator settings files known to hold an ``AppId = <number>`` line."""

_APPID_LINE = re.compile(r"^\s*app_?id\s*=\s*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
_GOG_INFO = re.compile(r"goggame-(\d+)\.info", re.IGNORECASE)


@dataclass
class Identification:
    steam_app_id: int | None = None
    gog_id: int | None = None
    name: str | None = None
    evidence: list[Path] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.steam_app_id is not None or self.gog_id is not None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:65536]
    except OSError:
        return ""


def _walk(root: Path):
    root_depth = len(root.parts)
    for folder, dirs, files in os.walk(root):
        depth = len(Path(folder).parts) - root_depth
        dirs[:] = sorted(d for d in dirs if d.lower() not in SKIP_DIRS and depth < MAX_DEPTH)
        yield Path(folder), sorted(files)


def identify(folder: Path) -> Identification:
    result = Identification()
    for parent, files in _walk(Path(folder)):
        for name in files:
            path = parent / name
            lower = name.lower()
            if result.steam_app_id is None and lower == "steam_appid.txt":
                text = _read_text(path).strip()
                if text.isdigit() and int(text) > 0:
                    result.steam_app_id = int(text)
                    result.evidence.append(path)
            elif result.steam_app_id is None and lower in INI_FILES:
                match = _APPID_LINE.search(_read_text(path))
                if match and int(match.group(1)) > 0:
                    result.steam_app_id = int(match.group(1))
                    result.evidence.append(path)
            elif result.gog_id is None and (gog := _GOG_INFO.fullmatch(name)):
                result.gog_id = int(gog.group(1))
                result.evidence.append(path)
                try:
                    result.name = json.loads(_read_text(path)).get("name") or result.name
                except (json.JSONDecodeError, AttributeError):
                    pass
        if result.steam_app_id is not None and result.gog_id is not None:
            break
    return result
