"""The background runner: watches for play sessions and snapshots saves."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from saveix.core.backup import BackupEngine, BackupResult, NothingToBackUpError, utc_now
from saveix.core.catalog import Catalog
from saveix.core.context import context_for
from saveix.core.models import Game, Trigger
from saveix.core.sessions import EventKind, SessionDetector
from saveix.core.watcher import ChangeTracker, FolderWatcher, WatchdogWatcher, watch_game

log = logging.getLogger("saveix")


@dataclass
class Notice:
    """Something the runner wants the user to know about."""

    game: str
    message: str
    warning: bool = False


class Runner:
    def __init__(
        self,
        catalog: Catalog,
        engine: BackupEngine,
        detector: SessionDetector | None = None,
        clock: Callable[[], str] = utc_now,
        notify: Callable[[Notice], None] | None = None,
        retention: Callable[[Game], list[str]] | None = None,
        quiet_period: float = 10.0,
        checkpoint_interval: float = 600.0,
        watcher_factory: Callable[[], FolderWatcher] = WatchdogWatcher,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.catalog = catalog
        self.engine = engine
        self.detector = detector or SessionDetector()
        self.clock = clock
        self.notify = notify or (lambda notice: None)
        self.retention = retention
        self.quiet_period = quiet_period
        self.checkpoint_interval = checkpoint_interval
        self.watcher_factory = watcher_factory
        self.monotonic = monotonic
        self.active: dict[int, _Active] = {}
        """Games being played, by game ID."""
        self._close_interrupted_sessions()

    def _close_interrupted_sessions(self) -> None:
        # Sessions left open when saveix itself was stopped.
        for session in self.catalog.open_sessions():
            self.catalog.end_session(session.id, self.clock())

    def _say(self, game: Game, message: str, warning: bool = False) -> None:
        (log.warning if warning else log.info)("%s: %s", game.name, message)
        self.notify(Notice(game.name, message, warning))

    def poll(self) -> None:
        games = self.catalog.list_games()
        for event in self.detector.poll(games):
            if event.kind is EventKind.STARTED:
                self._session_started(event.game)
            else:
                self._session_ended(event.game, event.crashed)
        now = self.monotonic()
        for active in list(self.active.values()):
            if active.tracker.due(now) and self._gap_passed(active, now):
                active.tracker.reset()
                active.last_checkpoint = now
                self.snapshot(active.game, Trigger.CHECKPOINT, active.session_id)

    def _gap_passed(self, active: _Active, now: float) -> bool:
        """Checkpoints are at least the game's interval apart; later saves wait for the
        next allowed checkpoint or the end of the session."""
        minutes = active.game.checkpoint_interval_minutes
        gap = self.checkpoint_interval if minutes is None else minutes * 60
        return active.last_checkpoint is None or now - active.last_checkpoint >= gap

    def _session_started(self, game: Game) -> None:
        session = self.catalog.start_session(game, self.clock())
        context = context_for(game)
        tracker = ChangeTracker(game, context, self.quiet_period)
        watcher = self.watcher_factory()
        try:
            watch_game(game, context, tracker, watcher, self.monotonic)
        except Exception:
            log.exception("%s: could not watch save folders", game.name)
        self.active[game.id] = _Active(game, session.id, tracker, watcher)
        self._say(game, "session started")

    def _session_ended(self, game: Game, crashed: bool) -> None:
        active = self.active.pop(game.id, None)
        session_id = None
        if active:
            active.watcher.stop()
            session_id = active.session_id
        self.snapshot(game, Trigger.SESSION_END, session_id, crashed)
        if session_id is not None:
            self.catalog.end_session(session_id, self.clock(), crashed)
        self._say(game, "session ended after a crash" if crashed else "session ended", crashed)
        if self.retention:
            try:
                for warning in self.retention(game):
                    self._say(game, warning, warning=True)
            except Exception:
                log.exception("%s: thinning old snapshots failed", game.name)

    def stop_watching(self) -> None:
        for active in self.active.values():
            active.watcher.stop()

    def snapshot(
        self, game: Game, trigger: Trigger, session_id: int | None, crashed: bool = False
    ) -> BackupResult | None:
        try:
            result = self.engine.backup(game, context_for(game), trigger, session_id, crashed)
        except NothingToBackUpError as exc:
            self._say(game, str(exc), warning=True)
            return None
        except Exception:
            log.exception("%s: backup failed", game.name)
            self._say(game, "backup failed; see the log", warning=True)
            return None
        for path, reason in result.skipped:
            self._say(game, f"skipped {path}: {reason}", warning=True)
        snap = result.snapshot
        if snap and snap.health == "suspicious":
            problems = "; ".join(snap.health_notes)
            self._say(game, f"snapshot #{snap.id} looks damaged: {problems}", warning=True)
        elif snap:
            self._say(game, f"saved snapshot #{snap.id}")
        return result

    def run(self, stop: threading.Event, interval: float = 5.0) -> None:
        log.info("watching for game sessions")
        while not stop.is_set():
            try:
                self.poll()
            except Exception:
                log.exception("polling failed")
            stop.wait(interval)
        self.stop_watching()


@dataclass
class _Active:
    game: Game
    session_id: int
    tracker: ChangeTracker
    watcher: FolderWatcher
    last_checkpoint: float | None = None
