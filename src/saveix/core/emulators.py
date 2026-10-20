"""Find where Steam emulators keep a game's Steam Cloud files.

Save locations are often documented as Steam's own cloud folder
(``Steam/userdata/<user>/<appid>/remote``). Copies running on a Steam emulator write
the same files to the emulator's folder instead. Source templates can refer to the
game's Steam cloud folder as ``<steamremote>``; this module turns that into the
emulator folders that actually exist on this PC.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from saveix.core.paths import PathContext, UnresolvedPlaceholderError

STEAM_REMOTE = "<steamremote>"


@dataclass(frozen=True)
class Emulator:
    name: str
    remote: str
    """Template of the emulator's remote folder, with ``{appid}`` for the app ID."""
    verified: bool = False

    def remote_for(self, app_id: int) -> str:
        return self.remote.replace("{appid}", str(app_id))


@dataclass(frozen=True)
class EmulatorMatch:
    emulator: Emulator
    template: str


def _parse(data: dict) -> list[Emulator]:
    return [
        Emulator(e["name"], e["remote"], bool(e.get("verified", False)))
        for e in data.get("emulators", [])
        if "{appid}" in e.get("remote", "")
    ]


def load_emulators(user_file: Path | None = None) -> list[Emulator]:
    """The built-in list plus any user additions (same JSON format)."""
    builtin = json.loads(resources.files("saveix.core.data").joinpath("emulators.json").read_text())
    emulators = _parse(builtin)
    if user_file and user_file.exists():
        extra = _parse(json.loads(user_file.read_text(encoding="utf-8")))
        names = {e.name for e in extra}
        emulators = extra + [e for e in emulators if e.name not in names]
    return emulators


def find_remote_folders(
    app_id: int, context: PathContext, emulators: list[Emulator]
) -> list[EmulatorMatch]:
    """Emulator cloud folders for this app ID that exist on this PC."""
    matches = []
    for emulator in emulators:
        template = emulator.remote_for(app_id)
        try:
            if Path(context.expand(template)).is_dir():
                matches.append(EmulatorMatch(emulator, template))
        except UnresolvedPlaceholderError:
            continue
    return matches


def translate(
    template: str, app_id: int, context: PathContext, emulators: list[Emulator]
) -> list[EmulatorMatch]:
    """Turn a ``<steamremote>/...`` template into templates for existing emulator folders."""
    if not template.startswith(STEAM_REMOTE):
        return []
    rest = template[len(STEAM_REMOTE) :]
    return [
        EmulatorMatch(m.emulator, m.template + rest)
        for m in find_remote_folders(app_id, context, emulators)
    ]
