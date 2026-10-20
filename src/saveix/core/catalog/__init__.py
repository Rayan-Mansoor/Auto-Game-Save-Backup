"""SQLite catalog of games, save sources and snapshots."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from saveix.core.catalog import migrations
from saveix.core.models import (
    Game,
    Session,
    Snapshot,
    SnapshotFile,
    Source,
    SourceKind,
    SourceRole,
    Trigger,
)


class CatalogError(Exception):
    pass


class Catalog:
    def __init__(self, path: Path | str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        migrations.apply(self.db)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Catalog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # games

    def add_game(self, name: str) -> Game:
        name = name.strip()
        if not name:
            raise CatalogError("Game name must not be empty")
        try:
            cur = self.db.execute("INSERT INTO games (name) VALUES (?)", (name,))
        except sqlite3.IntegrityError:
            raise CatalogError(f"A game named '{name}' already exists") from None
        return Game(name=name, id=cur.lastrowid)

    def get_game(self, name: str) -> Game:
        row = self.db.execute("SELECT * FROM games WHERE name = ?", (name.strip(),)).fetchone()
        if row is None:
            raise CatalogError(f"No game named '{name}'")
        return self._game(row)

    def list_games(self) -> list[Game]:
        rows = self.db.execute("SELECT * FROM games ORDER BY name COLLATE NOCASE").fetchall()
        return [self._game(row) for row in rows]

    def remove_game(self, name: str) -> None:
        game = self.get_game(name)
        self.db.execute("DELETE FROM games WHERE id = ?", (game.id,))

    def set_install_dir(self, game: Game, install_dir: str | None) -> None:
        self._set_game_column(game, "install_dir", install_dir)
        game.install_dir = install_dir

    def set_store_ids(self, game: Game, steam_app_id: int | None, gog_id: int | None) -> None:
        self._set_game_column(game, "steam_app_id", steam_app_id)
        self._set_game_column(game, "gog_id", gog_id)
        game.steam_app_id, game.gog_id = steam_app_id, gog_id

    def set_executables(self, game: Game, executables: list[str]) -> None:
        self._set_game_column(game, "executables", json.dumps(executables))
        game.executables = list(executables)

    def set_checkpoint_interval(self, game: Game, minutes: int | None) -> None:
        self._set_game_column(game, "checkpoint_interval_minutes", minutes)
        game.checkpoint_interval_minutes = minutes

    def _set_game_column(self, game: Game, column: str, value: object) -> None:
        self.db.execute(f"UPDATE games SET {column} = ? WHERE id = ?", (value, game.id))

    def _game(self, row: sqlite3.Row) -> Game:
        game = Game(
            name=row["name"],
            id=row["id"],
            install_dir=row["install_dir"],
            steam_app_id=row["steam_app_id"],
            gog_id=row["gog_id"],
            executables=json.loads(row["executables"]),
            checkpoint_interval_minutes=row["checkpoint_interval_minutes"],
        )
        game.sources = self.sources_for(game.id)
        return game

    # sources

    def add_source(self, game: Game, source: Source) -> Source:
        try:
            cur = self.db.execute(
                "INSERT INTO sources (game_id, kind, path, role, include, exclude, origin)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    game.id,
                    source.kind.value,
                    source.path,
                    source.role.value,
                    json.dumps(source.include),
                    json.dumps(source.exclude),
                    source.origin,
                ),
            )
        except sqlite3.IntegrityError:
            raise CatalogError(f"'{source.path}' is already a source of {game.name}") from None
        source.id = cur.lastrowid
        source.game_id = game.id
        game.sources.append(source)
        return source

    def remove_source(self, game: Game, source_id: int) -> None:
        cur = self.db.execute(
            "DELETE FROM sources WHERE id = ? AND game_id = ?", (source_id, game.id)
        )
        if cur.rowcount == 0:
            raise CatalogError(f"{game.name} has no source with id {source_id}")
        game.sources = [s for s in game.sources if s.id != source_id]

    def sources_for(self, game_id: int) -> list[Source]:
        rows = self.db.execute(
            "SELECT * FROM sources WHERE game_id = ? ORDER BY id", (game_id,)
        ).fetchall()
        return [
            Source(
                kind=SourceKind(row["kind"]),
                path=row["path"],
                role=SourceRole(row["role"]),
                include=json.loads(row["include"]),
                exclude=json.loads(row["exclude"]),
                origin=row["origin"],
                id=row["id"],
                game_id=row["game_id"],
            )
            for row in rows
        ]

    # snapshots

    def add_snapshot(
        self,
        game: Game,
        trigger: Trigger,
        created_at: str,
        fingerprint: str,
        files: list[SnapshotFile],
        session_id: int | None = None,
    ) -> Snapshot:
        self.db.execute("BEGIN")
        try:
            cur = self.db.execute(
                "INSERT INTO snapshots"
                " (game_id, created_at, trigger, file_count, total_size, fingerprint, session_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    game.id,
                    created_at,
                    trigger.value,
                    len(files),
                    sum(f.size for f in files),
                    fingerprint,
                    session_id,
                ),
            )
            snapshot_id = cur.lastrowid
            self.db.executemany(
                "INSERT INTO snapshot_files"
                " (snapshot_id, source_id, source_path, template, digest, size, mtime_ns)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        snapshot_id,
                        f.source_id,
                        f.source_path,
                        f.template,
                        f.digest,
                        f.size,
                        f.mtime_ns,
                    )
                    for f in files
                ],
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.get_snapshot(snapshot_id)

    def get_snapshot(self, snapshot_id: int) -> Snapshot:
        row = self.db.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise CatalogError(f"No snapshot #{snapshot_id}")
        return self._snapshot(row)

    def snapshots(self, game: Game) -> list[Snapshot]:
        rows = self.db.execute(
            "SELECT * FROM snapshots WHERE game_id = ? ORDER BY id", (game.id,)
        ).fetchall()
        return [self._snapshot(row) for row in rows]

    def latest_snapshot(self, game: Game) -> Snapshot | None:
        row = self.db.execute(
            "SELECT * FROM snapshots WHERE game_id = ? ORDER BY id DESC LIMIT 1", (game.id,)
        ).fetchone()
        return self._snapshot(row) if row else None

    def snapshot_files(self, snapshot_id: int) -> list[SnapshotFile]:
        rows = self.db.execute(
            "SELECT * FROM snapshot_files WHERE snapshot_id = ? ORDER BY template", (snapshot_id,)
        ).fetchall()
        return [
            SnapshotFile(
                source_id=row["source_id"],
                source_path=row["source_path"],
                template=row["template"],
                digest=row["digest"],
                size=row["size"],
                mtime_ns=row["mtime_ns"],
            )
            for row in rows
        ]

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> Snapshot:
        return Snapshot(
            id=row["id"],
            game_id=row["game_id"],
            created_at=row["created_at"],
            trigger=Trigger(row["trigger"]),
            file_count=row["file_count"],
            total_size=row["total_size"],
            fingerprint=row["fingerprint"],
            label=row["label"],
            note=row["note"],
            session_id=row["session_id"],
            health=row["health"],
            health_notes=json.loads(row["health_notes"]),
        )

    def set_label(self, snapshot_id: int, label: str | None) -> Snapshot:
        return self._update_snapshot(snapshot_id, "label", label)

    def set_note(self, snapshot_id: int, note: str | None) -> Snapshot:
        return self._update_snapshot(snapshot_id, "note", note)

    def _update_snapshot(self, snapshot_id: int, column: str, value: str | None) -> Snapshot:
        value = (value or "").strip() or None
        self.get_snapshot(snapshot_id)
        self.db.execute(f"UPDATE snapshots SET {column} = ? WHERE id = ?", (value, snapshot_id))
        return self.get_snapshot(snapshot_id)

    def set_health(self, snapshot_id: int, health: str, notes: list[str]) -> Snapshot:
        self.db.execute(
            "UPDATE snapshots SET health = ?, health_notes = ? WHERE id = ?",
            (health, json.dumps(notes), snapshot_id),
        )
        return self.get_snapshot(snapshot_id)

    def previous_snapshot(self, snapshot: Snapshot) -> Snapshot | None:
        row = self.db.execute(
            "SELECT * FROM snapshots WHERE game_id = ? AND id < ? ORDER BY id DESC LIMIT 1",
            (snapshot.game_id, snapshot.id),
        ).fetchone()
        return self._snapshot(row) if row else None

    # sessions

    def start_session(self, game: Game, started_at: str) -> Session:
        cur = self.db.execute(
            "INSERT INTO sessions (game_id, started_at) VALUES (?, ?)", (game.id, started_at)
        )
        return self.get_session(cur.lastrowid)

    def end_session(self, session_id: int, ended_at: str, crashed: bool = False) -> Session:
        self.db.execute(
            "UPDATE sessions SET ended_at = ?, crashed = ? WHERE id = ?",
            (ended_at, int(crashed), session_id),
        )
        return self.get_session(session_id)

    def get_session(self, session_id: int) -> Session:
        row = self.db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise CatalogError(f"No session #{session_id}")
        return self._session(row)

    def sessions(self, game: Game) -> list[Session]:
        rows = self.db.execute(
            "SELECT * FROM sessions WHERE game_id = ? ORDER BY id", (game.id,)
        ).fetchall()
        return [self._session(row) for row in rows]

    def open_sessions(self) -> list[Session]:
        rows = self.db.execute("SELECT * FROM sessions WHERE ended_at IS NULL").fetchall()
        return [self._session(row) for row in rows]

    @staticmethod
    def _session(row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            game_id=row["game_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            crashed=bool(row["crashed"]),
        )
