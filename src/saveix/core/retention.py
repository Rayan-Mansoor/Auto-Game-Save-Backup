"""Which snapshots to keep as a game's history grows.

This module decides; it never deletes anything itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from saveix.core.models import Snapshot, Trigger
from saveix.core.timeline import parse_time

SAFETY_KEEP_DAYS = 30


def protected(snapshots: list[Snapshot], now: datetime) -> dict[int, str]:
    """Snapshots that must never be removed automatically, with the reason why.

    ``snapshots`` are one game's snapshots in the order they were taken.
    """
    reasons: dict[int, str] = {}

    def protect(snapshot: Snapshot, reason: str) -> None:
        reasons.setdefault(snapshot.id, reason)

    for snap in snapshots:
        if snap.pinned:
            protect(snap, "pinned")
        elif snap.label:
            protect(snap, "labeled")
        elif snap.trigger is Trigger.SAFETY and now - parse_time(snap.created_at) < timedelta(
            days=SAFETY_KEEP_DAYS
        ):
            protect(snap, "recent safety snapshot")
    if snapshots:
        protect(snapshots[-1], "latest")

    # The last good state before anything went wrong, and the newest good state overall.
    last_healthy: Snapshot | None = None
    for snap in snapshots:
        if snap.health == "suspicious" and last_healthy is not None:
            protect(last_healthy, f"last healthy before #{snap.id}")
        elif snap.health == "ok":
            last_healthy = snap
    if last_healthy is not None:
        protect(last_healthy, "newest healthy")
    return reasons
