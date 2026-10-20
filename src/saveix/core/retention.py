"""Which snapshots to keep as a game's history grows.

This module decides; it never deletes anything itself.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from pathlib import Path

from saveix.core.catalog import Catalog
from saveix.core.config import Config, Settings
from saveix.core.models import Game, Session, Snapshot, Trigger
from saveix.core.store import ObjectStore
from saveix.core.timeline import parse_time

SAFETY_KEEP_DAYS = 30
DAILY_PLAY_DAYS = 30
"""Play-days that keep one snapshot each; older play-days keep one per week."""


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


def _recent_session_ids(sessions: list[Session], recent_sessions: int) -> set[int]:
    if recent_sessions <= 0:
        return set()
    return {s.id for s in sorted(sessions, key=lambda s: s.id)[-recent_sessions:]}


def thin_sessions(
    snapshots: list[Snapshot], sessions: list[Session], recent_sessions: int
) -> list[Removal]:
    """Older sessions shrink to their final state (their last snapshot).

    Every snapshot of the most recent sessions is kept. If a session's last snapshot
    looks damaged, its newest healthy snapshot is kept too.
    """
    recent = _recent_session_ids(sessions, recent_sessions)
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


def thin_by_play_time(
    snapshots: list[Snapshot],
    sessions: list[Session],
    recent_sessions: int,
    daily_play_days: int = DAILY_PLAY_DAYS,
    tz: tzinfo | None = None,
) -> list[Removal]:
    """Older history keeps one snapshot per play-day, then one per play-week.

    Age is counted in days the game was actually played, so a game left alone for
    months keeps its history exactly as it was.
    """
    recent = _recent_session_ids(sessions, recent_sessions)

    def day_of(snap: Snapshot) -> date:
        return parse_time(snap.created_at).astimezone(tz).date()

    play_days = sorted({day_of(s) for s in snapshots}, reverse=True)
    daily = set(play_days[:daily_play_days])
    # Everything since the oldest recent session (or, without sessions, from the most
    # recent play-days) is the recent window and is never thinned.
    recent_starts = [parse_time(s.started_at) for s in sessions if s.id in recent]
    if recent_starts:
        window_start = min(recent_starts)
        in_window = lambda snap: parse_time(snap.created_at) >= window_start  # noqa: E731
    else:
        recent_days = set(play_days[: max(recent_sessions, 0)])
        in_window = lambda snap: day_of(snap) in recent_days  # noqa: E731

    buckets: dict[tuple, list[Snapshot]] = defaultdict(list)
    for snap in snapshots:
        if snap.session_id in recent or in_window(snap):
            continue
        day = day_of(snap)
        if day in daily:
            buckets[("day", day)].append(snap)
        else:
            buckets[("week", *day.isocalendar()[:2])].append(snap)

    removals = []
    for (kind, *_), snaps in buckets.items():
        # Keep the latest state of each day or week.
        for snap in snaps[:-1]:
            period = "play-day" if kind == "day" else "play-week"
            removals.append(Removal(snap, f"older {period} keeps only its last snapshot"))
    return removals


def plan_removals(
    snapshots: list[Snapshot],
    sessions: list[Session],
    now: datetime,
    recent_sessions: int,
    tz: tzinfo | None = None,
) -> list[Removal]:
    """Everything the retention rules would remove, never including protected snapshots."""
    keep = protected(snapshots, now)
    removals = thin_sessions(snapshots, sessions, recent_sessions) + thin_by_play_time(
        snapshots, sessions, recent_sessions, tz=tz
    )
    seen: set[int] = set()
    result = []
    for removal in removals:
        if removal.snapshot.id in keep or removal.snapshot.id in seen:
            continue
        seen.add(removal.snapshot.id)
        result.append(removal)
    return sorted(result, key=lambda r: r.snapshot.id)


def prune(
    catalog: Catalog,
    game: Game,
    now: datetime,
    recent_sessions: int,
    dry_run: bool = False,
    tz: tzinfo | None = None,
) -> list[Removal]:
    removals = plan_removals(
        catalog.snapshots(game), catalog.sessions(game), now, recent_sessions, tz
    )
    if not dry_run:
        for removal in removals:
            catalog.delete_snapshot(removal.snapshot.id)
    return removals


@dataclass
class RetentionReport:
    removals: list[Removal]
    warnings: list[str]


def limit_count(
    snapshots: list[Snapshot], already_removed: set[int], max_count: int, now: datetime
) -> tuple[list[Removal], str | None]:
    """Remove the oldest unprotected snapshots until a game is within the count limit."""
    remaining = [s for s in snapshots if s.id not in already_removed]
    if max_count <= 0 or len(remaining) <= max_count:
        return [], None
    keep = protected(remaining, now)
    excess = len(remaining) - max_count
    candidates = [s for s in remaining if s.id not in keep][:excess]
    removals = [Removal(s, f"over the limit of {max_count} snapshots") for s in candidates]
    warning = None
    if len(candidates) < excess:
        warning = (
            f"{len(remaining) - len(candidates)} snapshots are kept, above the limit of "
            f"{max_count}, because the rest are protected"
        )
    return removals, warning


def apply_policy(
    catalog: Catalog,
    game: Game,
    settings: Settings,
    now: datetime,
    dry_run: bool = False,
    tz: tzinfo | None = None,
) -> RetentionReport:
    """Apply the retention rules and the per-game snapshot limit to one game."""
    if settings.keep_all_snapshots:
        return RetentionReport([], [])
    snapshots = catalog.snapshots(game)
    removals = plan_removals(
        snapshots, catalog.sessions(game), now, settings.recent_sessions_kept, tz
    )
    extra, warning = limit_count(
        snapshots, {r.snapshot.id for r in removals}, settings.max_snapshots_per_game, now
    )
    removals += extra
    if not dry_run:
        for removal in removals:
            catalog.delete_snapshot(removal.snapshot.id)
    return RetentionReport(removals, [f"{game.name}: {warning}"] if warning else [])


def apply_storage_limit(
    catalog: Catalog,
    store: ObjectStore,
    settings: Settings,
    now: datetime,
    dry_run: bool = False,
) -> RetentionReport:
    """Remove the oldest unprotected snapshots of any game until the store fits its limit."""
    limit = settings.max_storage_mb * 1024 * 1024
    if settings.keep_all_snapshots or limit <= 0:
        return RetentionReport([], [])

    sizes: dict[str, int] = {}

    def size_of(digest: str) -> int:
        if digest not in sizes:
            try:
                sizes[digest] = store.stored_size(digest)
            except OSError:
                sizes[digest] = 0
        return sizes[digest]

    uses = catalog.digest_use_counts()
    used = sum(size_of(d) for d in uses)
    candidates: list[Snapshot] = []
    for game in catalog.list_games():
        snaps = catalog.snapshots(game)
        keep = protected(snaps, now)
        candidates += [s for s in snaps if s.id not in keep]
    candidates.sort(key=lambda s: s.created_at)

    removals = []
    for snap in candidates:
        if used <= limit:
            break
        for digest in catalog.snapshot_digests(snap.id):
            uses[digest] -= 1
            if uses[digest] == 0:
                used -= size_of(digest)
        removals.append(Removal(snap, f"backups are over {settings.max_storage_mb} MB"))
        if not dry_run:
            catalog.delete_snapshot(snap.id)
    warnings = []
    if used > limit:
        warnings.append(
            f"Backups use {used // (1024 * 1024)} MB, above the {settings.max_storage_mb} MB "
            "limit, because the remaining snapshots are protected"
        )
    return RetentionReport(removals, warnings)


def retention_hook(config: Config, catalog: Catalog) -> Callable[[Game], list[str]]:
    """What the runner calls after each session; returns warnings to show the user."""
    from saveix.core.gc import collect_garbage

    def run(game: Game) -> list[str]:
        now = datetime.now(UTC)
        store = ObjectStore(config.backup_root)
        report = apply_policy(catalog, game, config.settings, now)
        storage = apply_storage_limit(catalog, store, config.settings, now)
        collect_garbage(catalog, store)
        warnings = report.warnings + storage.warnings
        if config.settings.mirror_dir:
            from saveix.core.mirror import mirror

            try:
                mirror(catalog, store, Path(config.settings.mirror_dir).expanduser())
            except OSError as exc:
                warnings.append(f"Could not update the backup mirror: {exc}")
        return warnings

    return run
