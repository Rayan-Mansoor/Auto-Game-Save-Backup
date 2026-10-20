"""SQLite catalog of games, save sources and snapshots."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from saveix.core.catalog import migrations
from saveix.core.models import Game, Source, SourceKind, SourceRole


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

    def _game(self, row: sqlite3.Row) -> Game:
        game = Game(name=row["name"], id=row["id"])
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
