"""Portable save paths.

Save locations are stored as templates with saveix's own placeholders, such as
``<appdata>/Game/saves``, so a backup can be restored on another PC or user account.
``PathContext`` turns templates into real paths (``expand``) and back (``collapse``).
"""

from __future__ import annotations

import glob
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

HOME = "<home>"
APPDATA = "<appdata>"
LOCALAPPDATA = "<localappdata>"
LOCALLOW = "<locallow>"
DOCUMENTS = "<documents>"
SAVEDGAMES = "<savedgames>"
PUBLIC = "<public>"
PROGRAMDATA = "<programdata>"
INSTALL = "<install>"
USERID = "<userid>"

FOLDER_PLACEHOLDERS = (
    HOME,
    APPDATA,
    LOCALAPPDATA,
    LOCALLOW,
    DOCUMENTS,
    SAVEDGAMES,
    PUBLIC,
    PROGRAMDATA,
)
ALL_PLACEHOLDERS = (*FOLDER_PLACEHOLDERS, INSTALL, USERID)

_PLACEHOLDER_RE = re.compile(r"<[a-z]+>")


class UnresolvedPlaceholderError(ValueError):
    """A template uses a placeholder that has no value in this context."""


class FolderProvider(Protocol):
    def known_folders(self) -> dict[str, Path]:
        """Return a mapping of folder placeholder to its real location."""
        ...


def normalize(path: str | os.PathLike[str]) -> str:
    """Use forward slashes and drop trailing separators."""
    text = str(path).replace("\\", "/")
    while len(text) > 1 and text.endswith("/") and not text.endswith(":/"):
        text = text[:-1]
    return text


@dataclass(frozen=True)
class StaticFolders:
    """Folder locations given explicitly (tests, or another PC's layout)."""

    folders: Mapping[str, Path]

    def known_folders(self) -> dict[str, Path]:
        return dict(self.folders)


class WindowsFolders:
    """Looks up the user's real folders with the Windows known-folder API."""

    _GUIDS = {
        HOME: "5E6C858F-0E22-4760-9AFE-EA3317B67173",
        APPDATA: "3EB685DB-65F9-4CF6-A03A-E3EF65729F3D",
        LOCALAPPDATA: "F1B32785-6FBA-4FCF-9D55-7B8E7F157091",
        LOCALLOW: "A520A1A4-1780-4FF6-BD18-167343C5AF16",
        DOCUMENTS: "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
        SAVEDGAMES: "4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4",
        PUBLIC: "DFDF76A2-C82A-4D63-906A-5644AC457385",
        PROGRAMDATA: "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97",
    }

    def known_folders(self) -> dict[str, Path]:
        result = {}
        for placeholder, guid in self._GUIDS.items():
            location = self._known_folder(guid)
            if location:
                result[placeholder] = Path(location)
        return result

    @staticmethod
    def _known_folder(guid_text: str) -> str | None:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        guid = GUID.from_buffer_copy(uuid.UUID(guid_text).bytes_le)
        path_ptr = ctypes.c_wchar_p()
        hresult = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(path_ptr)
        )
        try:
            return path_ptr.value if hresult == 0 else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)


class FallbackFolders:
    """Windows-style folder layout under the home folder, for non-Windows systems."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or Path.home()

    def known_folders(self) -> dict[str, Path]:
        return {
            HOME: self.home,
            APPDATA: self.home / "AppData" / "Roaming",
            LOCALAPPDATA: self.home / "AppData" / "Local",
            LOCALLOW: self.home / "AppData" / "LocalLow",
            DOCUMENTS: self.home / "Documents",
            SAVEDGAMES: self.home / "Saved Games",
            PUBLIC: Path(os.environ.get("PUBLIC", "/Users/Shared")),
            PROGRAMDATA: Path(os.environ.get("PROGRAMDATA", "/Library/Application Support")),
        }


def system_folders() -> FolderProvider:
    return WindowsFolders() if sys.platform == "win32" else FallbackFolders()


@dataclass
class PathContext:
    """Values for every placeholder, used to expand and collapse save paths."""

    folders: dict[str, Path]
    install: Path | None = None
    user_id: str | None = None
    _ordered: list[tuple[str, str]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        pairs = [(name, normalize(path)) for name, path in self.folders.items()]
        if self.install is not None:
            pairs.append((INSTALL, normalize(self.install)))
        # Longest prefix first, so the most specific placeholder wins when collapsing.
        self._ordered = sorted(pairs, key=lambda pair: len(pair[1]), reverse=True)

    @classmethod
    def for_system(cls, install: Path | None = None, user_id: str | None = None) -> PathContext:
        return cls(system_folders().known_folders(), install=install, user_id=user_id)

    def values(self) -> dict[str, str]:
        values = {name: path for name, path in self._ordered}
        # An unknown user ID matches any user's folder.
        values[USERID] = self.user_id or "*"
        return values

    def expand(self, template: str, escape: bool = False) -> str:
        """Replace placeholders with real locations. The result may still be a glob.

        With ``escape``, glob characters in the substituted folders are escaped, so the
        result can be passed to ``glob`` while only the template's own wildcards match.
        """
        values = self.values()
        if escape:
            values = {k: v if k == USERID else glob.escape(v) for k, v in values.items()}

        def replace(match: re.Match[str]) -> str:
            name = match.group(0)
            if name not in ALL_PLACEHOLDERS:
                return name
            if name not in values:
                raise UnresolvedPlaceholderError(f"{name} is not known on this PC")
            return values[name]

        return normalize(_PLACEHOLDER_RE.sub(replace, normalize(template)))

    def collapse(self, path: str | os.PathLike[str]) -> str:
        """Turn a real path into a template using the most specific matching placeholder."""
        text = normalize(path)
        folded = text.casefold()
        for name, prefix in self._ordered:
            prefix_folded = prefix.casefold()
            if folded == prefix_folded:
                return name
            if folded.startswith(prefix_folded.rstrip("/") + "/"):
                return name + text[len(prefix.rstrip("/")) :]
        return text


def placeholders_in(template: str) -> set[str]:
    return {name for name in _PLACEHOLDER_RE.findall(template) if name in ALL_PLACEHOLDERS}
