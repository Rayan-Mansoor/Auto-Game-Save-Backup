"""A game's snapshot history, described for people."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from saveix.core.catalog import Catalog
from saveix.core.models import Game, Snapshot, Trigger

AUTO_LABELS = {
    Trigger.MANUAL: "Manual backup",
    Trigger.CHECKPOINT: "Checkpoint",
    Trigger.SESSION_END: "End of session",
    Trigger.SAFETY: "Before restore",
}


@dataclass
class TimelineEntry:
    snapshot: Snapshot
    label: str
    custom_label: bool

    @property
    def local_time(self) -> datetime:
        return parse_time(self.snapshot.created_at).astimezone()


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def auto_label(snapshot: Snapshot) -> str:
    return AUTO_LABELS[snapshot.trigger]


def timeline(catalog: Catalog, game: Game) -> list[TimelineEntry]:
    """Every snapshot of a game, newest first."""
    entries = []
    for snapshot in reversed(catalog.snapshots(game)):
        if snapshot.label:
            entries.append(TimelineEntry(snapshot, snapshot.label, True))
        else:
            entries.append(TimelineEntry(snapshot, auto_label(snapshot), False))
    return entries
