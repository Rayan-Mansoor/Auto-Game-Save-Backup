"""Turn Ludusavi manifest entries into saveix source candidates.

This is the only place that knows Ludusavi's path format. Everything leaving the
provider uses saveix's own placeholders.
"""

from __future__ import annotations

import re

from saveix.core.models import SourceKind, SourceRole
from saveix.core.providers import GameDetails, GameMatch, SourceCandidate
from saveix.core.sources.registry import RegistryError, normalize_key

# Longest first: specific home sub-folders map to saveix's dedicated placeholders.
PREFIXES = [
    ("<home>/AppData/LocalLow", "<locallow>"),
    ("<home>/AppData/Local", "<localappdata>"),
    ("<home>/AppData/Roaming", "<appdata>"),
    ("<home>/Saved Games", "<savedgames>"),
    ("<home>/Documents", "<documents>"),
    ("<winLocalAppDataLow>", "<locallow>"),
    ("<winLocalAppData>", "<localappdata>"),
    ("<winAppData>", "<appdata>"),
    ("<winDocuments>", "<documents>"),
    ("<winPublic>", "<public>"),
    ("<winProgramData>", "<programdata>"),
    ("<base>", "<install>"),
    ("<home>", "<home>"),
]
UNSUPPORTED = ("<winDir>", "<xdgData>", "<xdgConfig>", "<osUserName>", "<game>")
_STEAM_REMOTE = re.compile(r"^<root>/userdata/<storeUserId>/(\d+)/remote(/.*)?$")


def _applies_to_windows(info: dict) -> bool:
    when = info.get("when") or []
    return not when or any(w.get("os") in (None, "windows") for w in when)


def _role(info: dict) -> SourceRole:
    tags = info.get("tags") or []
    return SourceRole.CONFIG if tags and "save" not in tags else SourceRole.SAVE


def translate_path(path: str, steam_id: int | None) -> str | None:
    """Ludusavi path to a saveix template, or None if it cannot be used on Windows."""
    remote = _STEAM_REMOTE.match(path)
    if remote:
        if steam_id is None or int(remote.group(1)) != steam_id:
            return None
        return "<steamremote>" + (remote.group(2) or "")
    for old, new in PREFIXES:
        if path == old or path.startswith(old + "/"):
            path = new + path[len(old) :]
            break
    else:
        return None
    if steam_id is not None:
        path = path.replace("<storeGameId>", str(steam_id))
    path = path.replace("<storeUserId>", "<userid>")
    if any(token in path for token in UNSUPPORTED) or "<root>" in path or "<storeGameId>" in path:
        return None
    return path


def translate_entry(match: GameMatch, entry: dict) -> GameDetails:
    steam_id = (entry.get("steam") or {}).get("id")
    candidates: list[SourceCandidate] = []
    for path, info in (entry.get("files") or {}).items():
        info = info or {}
        if not _applies_to_windows(info):
            continue
        template = translate_path(path, steam_id)
        if template:
            # Ludusavi paths are globs, and a matching folder includes everything in it.
            candidates.append(SourceCandidate(SourceKind.GLOB, template, _role(info)))
    for key, info in (entry.get("registry") or {}).items():
        try:
            candidates.append(
                SourceCandidate(SourceKind.REGISTRY, normalize_key(key), _role(info or {}))
            )
        except RegistryError:
            continue

    executables = []
    for path, launches in (entry.get("launch") or {}).items():
        name = path.rsplit("/", 1)[-1]
        windows = any(_applies_to_windows(launch or {}) for launch in launches or [{}])
        if windows and name.lower().endswith(".exe") and name not in executables:
            executables.append(name)

    cloud = entry.get("cloud") or {}
    return GameDetails(
        match,
        sources=list(dict.fromkeys(candidates)),
        executables=executables,
        cloud_sync=any(cloud.values()) if cloud else None,
    )
