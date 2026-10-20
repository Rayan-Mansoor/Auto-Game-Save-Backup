"""The background runner: watches for play sessions and snapshots saves."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from saveix.core.backup import BackupEngine, BackupResult, NothingToBackUpError, utc_now
from saveix.core.catalog import Catalog
from saveix.core.context import context_for
from saveix.core.models import Game, Trigger
from saveix.core.sessions import EventKind, SessionDetector

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
    ) -> None:
        self.catalog = catalog
        self.engine = engine
        self.detector = detector or SessionDetector()
        self.clock = clock
        self.notify = notify or (lambda notice: None)
        self.active: dict[int, int] = {}
        """Game ID to the ID of its running session."""
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
                session = self.catalog.start_session(event.game, self.clock())
                self.active[event.game.id] = session.id
                self._say(event.game, "session started")
            else:
                self._session_ended(event.game, event.crashed)

    def _session_ended(self, game: Game, crashed: bool) -> None:
        session_id = self.active.pop(game.id, None)
        self.snapshot(game, Trigger.SESSION_END, session_id)
        if session_id is not None:
            self.catalog.end_session(session_id, self.clock(), crashed)
        self._say(game, "session ended after a crash" if crashed else "session ended", crashed)

    def snapshot(self, game: Game, trigger: Trigger, session_id: int | None) -> BackupResult | None:
        try:
            result = self.engine.backup(game, context_for(game), trigger, session_id)
        except NothingToBackUpError as exc:
            self._say(game, str(exc), warning=True)
            return None
        except Exception:
            log.exception("%s: backup failed", game.name)
            self._say(game, "backup failed; see the log", warning=True)
            return None
        for path, reason in result.skipped:
            self._say(game, f"skipped {path}: {reason}", warning=True)
        if result.snapshot:
            self._say(game, f"saved snapshot #{result.snapshot.id}")
        return result

    def run(self, stop: threading.Event, interval: float = 5.0) -> None:
        log.info("watching for game sessions")
        while not stop.is_set():
            try:
                self.poll()
            except Exception:
                log.exception("polling failed")
            stop.wait(interval)
