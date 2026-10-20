"""Detect play sessions by watching which processes are running.

A game counts as running while any process matches it: an executable listed on the
game, or any program started from inside its install folder (which also catches
launchers that start the real game as a child process).
"""

from __future__ import annotations

import ntpath
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from saveix.core.models import Game
from saveix.core.paths import normalize

IGNORED_IN_INSTALL = {
    "unitycrashhandler64.exe",
    "unitycrashhandler32.exe",
    "unins000.exe",
    "vc_redist.x64.exe",
    "vc_redist.x86.exe",
    "dxsetup.exe",
    "dotnetfx.exe",
}
"""Helpers found in game folders that do not mean the game itself is running."""

CRASH_REPORTERS = {"crashreportclient.exe", "crashpad_handler.exe", "werfault.exe"}


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    exe: str | None = None
    cmdline: tuple[str, ...] = ()


class ProcessSource(Protocol):
    def processes(self) -> Iterable[ProcessInfo]: ...


class PsutilProcesses:
    def processes(self) -> Iterable[ProcessInfo]:
        import psutil

        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            info = proc.info
            yield ProcessInfo(
                info["pid"], info["name"] or "", info["exe"], tuple(info["cmdline"] or ())
            )


def _basename(path: str) -> str:
    return ntpath.basename(path.replace("/", "\\")).casefold()


def matches_game(game: Game, process: ProcessInfo) -> bool:
    name = process.name.casefold()
    exe = normalize(process.exe).casefold() if process.exe else None
    for wanted in game.executables:
        if "/" in normalize(wanted):
            if exe and exe == normalize(wanted).casefold():
                return True
        elif name == wanted.casefold() or (exe and _basename(exe) == wanted.casefold()):
            return True
    if game.install_dir and exe and name not in IGNORED_IN_INSTALL | CRASH_REPORTERS:
        install = normalize(game.install_dir).casefold().rstrip("/") + "/"
        return exe.startswith(install)
    return False


class EventKind(StrEnum):
    STARTED = "started"
    ENDED = "ended"


@dataclass(frozen=True)
class SessionEvent:
    kind: EventKind
    game: Game
    crashed: bool = False


@dataclass
class _Running:
    pids: set[int] = field(default_factory=set)
    gone_since: float | None = None
    crashed: bool = False


class SessionDetector:
    """Turns repeated process polls into session started/ended events."""

    def __init__(
        self,
        processes: ProcessSource | None = None,
        end_grace_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.source = processes or PsutilProcesses()
        self.end_grace = end_grace_seconds
        self.clock = clock
        self.running: dict[int, _Running] = {}

    def is_running(self, game: Game) -> bool:
        state = self.running.get(game.id)
        return bool(state and state.pids)

    def poll(self, games: list[Game]) -> list[SessionEvent]:
        now = self.clock()
        processes = list(self.source.processes())
        events = []
        for game in games:
            pids = {p.pid for p in processes if matches_game(game, p)}
            state = self.running.get(game.id)
            if state is None:
                if pids:
                    self.running[game.id] = _Running(pids)
                    events.append(SessionEvent(EventKind.STARTED, game))
                continue
            if _crash_seen(game, state.pids | pids, processes):
                state.crashed = True
            if pids:
                state.pids, state.gone_since = pids, None
                continue
            # Wait a little before ending, in case a launcher is handing over to the game.
            if state.gone_since is None:
                state.gone_since = now
            if now - state.gone_since >= self.end_grace:
                del self.running[game.id]
                events.append(SessionEvent(EventKind.ENDED, game, crashed=state.crashed))
        return events


def _crash_seen(game: Game, pids: set[int], processes: list[ProcessInfo]) -> bool:
    """A crash reporter is handling one of the game's processes."""
    for p in processes:
        name = p.name.casefold()
        if name == "werfault.exe":
            args = [a.casefold() for a in p.cmdline]
            for flag, value in zip(args, args[1:], strict=False):
                if flag == "-p" and value.isdigit() and int(value) in pids:
                    return True
        elif name in CRASH_REPORTERS and game.install_dir and p.exe:
            install = normalize(game.install_dir).casefold().rstrip("/") + "/"
            if normalize(p.exe).casefold().startswith(install):
                return True
    return False


def running_games(games: list[Game], processes: ProcessSource | None = None) -> list[Game]:
    current = list((processes or PsutilProcesses()).processes())
    return [g for g in games if any(matches_game(g, p) for p in current)]
