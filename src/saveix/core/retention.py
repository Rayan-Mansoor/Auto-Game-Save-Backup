"""Which snapshots to keep as a game's history grows.

This module decides; it never deletes anything itself.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from saveix.core.catalog import Catalog
from saveix.core.models import Game, Session, Snapshot, Trigger
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


@dataclass(frozen=True)
class Removal:
    snapshot: Snapshot
    reason: str


def thin_sessions(
    snapshots: list[Snapshot], sessions: list[Session], recent_sessions: int
) -> list[Removal]:
    """Older sessions shrink to their final state (their last snapshot).

    Every snapshot of the most recent sessions is kept. If a session's last snapshot
    looks damaged, its newest healthy snapshot is kept too.
    """
    recent = {s.id for s in sorted(sessions, key=lambda s: s.id)[-recent_sessions:]}
    if recent_sessions <= 0:
        recent = set()
    by_session: dict[int, list[Snapshot]] = defaultdict(list)
    for snap in snapshots:
        if snap.session_id is not None:
            by_session[snap.session_id].append(snap)

    removals = []
    for session_id, snaps in by_session.items():
        if session_id in recent or len(snaps) < 2:
            continue
        keep = {snaps[-1].id}
        if snaps[-1].health == "suspicious":
            healthy = [s for s in snaps if s.health == "ok"]
            if healthy:
                keep.add(healthy[-1].id)
        for snap in snaps:
            if snap.id not in keep:
                removals.append(Removal(snap, f"older session #{session_id}, not its final state"))
    return removals


def plan_removals(
    snapshots: list[Snapshot],
    sessions: list[Session],
    now: datetime,
    recent_sessions: int,
) -> list[Removal]:
    """Everything the retention rules would remove, never including protected snapshots."""
    keep = protected(snapshots, now)
    removals = thin_sessions(snapshots, sessions, recent_sessions)
    seen: set[int] = set()
    result = []
    for removal in removals:
        if removal.snapshot.id in keep or removal.snapshot.id in seen:
            continue
        seen.add(removal.snapshot.id)
        result.append(removal)
    return sorted(result, key=lambda r: r.snapshot.id)


def prune(
    catalog: Catalog, game: Game, now: datetime, recent_sessions: int, dry_run: bool = False
) -> list[Removal]:
    removals = plan_removals(catalog.snapshots(game), catalog.sessions(game), now, recent_sessions)
    if not dry_run:
        for removal in removals:
            catalog.delete_snapshot(removal.snapshot.id)
    return removals
