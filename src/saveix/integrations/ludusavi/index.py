"""A local SQLite index of the Ludusavi manifest for fast searching.

Parsing the full YAML manifest takes several seconds, so it is done once after each
download. Only entries that say where saves are kept are indexed.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

import yaml

INDEX_VERSION = 1


def normalize_name(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", text.casefold())


def _load_yaml(path: Path) -> dict:
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=loader) or {}


def _has_save_info(entry: dict) -> bool:
    return bool(entry.get("files") or entry.get("registry"))


def build_index(manifest: Path, index: Path) -> int:
    """Rebuild the index from the manifest; returns the number of games indexed."""
    data = _load_yaml(manifest)
    tmp = index.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    try:
        db.executescript(
            """
            CREATE TABLE games (name TEXT PRIMARY KEY, norm TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE names (norm TEXT NOT NULL, display TEXT NOT NULL, game TEXT NOT NULL);
            CREATE TABLE store_ids (store TEXT NOT NULL, id INTEGER NOT NULL, game TEXT NOT NULL);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        count = 0
        for name, entry in data.items():
            if not isinstance(entry, dict) or "alias" in entry or not _has_save_info(entry):
                continue
            count += 1
            db.execute(
                "INSERT INTO games VALUES (?, ?, ?)",
                (name, normalize_name(name), json.dumps(entry)),
            )
            db.execute("INSERT INTO names VALUES (?, ?, ?)", (normalize_name(name), name, name))
            ids = entry.get("id") or {}
            for store, primary, extra in (
                ("steam", (entry.get("steam") or {}).get("id"), ids.get("steamExtra")),
                ("gog", (entry.get("gog") or {}).get("id"), ids.get("gogExtra")),
            ):
                for value in [primary, *(extra or [])]:
                    if isinstance(value, int):
                        db.execute("INSERT INTO store_ids VALUES (?, ?, ?)", (store, value, name))
        for name, entry in data.items():
            target = entry.get("alias") if isinstance(entry, dict) else None
            if target:
                db.execute(
                    "INSERT INTO names SELECT ?, ?, name FROM games WHERE name = ?",
                    (normalize_name(name), name, target),
                )
        db.executescript(
            "CREATE INDEX names_norm ON names (norm);"
            "CREATE INDEX store_ids_lookup ON store_ids (store, id);"
        )
        db.execute("INSERT INTO meta VALUES ('version', ?)", (str(INDEX_VERSION),))
        db.execute(
            "INSERT INTO meta VALUES ('manifest_mtime', ?)", (str(manifest.stat().st_mtime_ns),)
        )
        db.commit()
    finally:
        db.close()
    os.replace(tmp, index)
    return count


def index_is_current(manifest: Path, index: Path) -> bool:
    if not index.exists():
        return False
    db = sqlite3.connect(index)
    try:
        meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.DatabaseError:
        return False
    finally:
        db.close()
    return meta.get("version") == str(INDEX_VERSION) and meta.get("manifest_mtime") == str(
        manifest.stat().st_mtime_ns
    )


class ManifestIndex:
    def __init__(self, path: Path) -> None:
        self.db = sqlite3.connect(path)

    def close(self) -> None:
        self.db.close()

    def search(self, query: str, limit: int = 10) -> list[str]:
        """Game names matching the query: exact names first, then prefixes, then the rest."""
        norm = normalize_name(query)
        if not norm:
            return []
        words = [normalize_name(w) for w in query.split() if normalize_name(w)]
        results: list[str] = []

        def add(rows):
            for (game,) in rows:
                if game not in results:
                    results.append(game)

        add(self.db.execute("SELECT game FROM names WHERE norm = ? ORDER BY game", (norm,)))
        add(
            self.db.execute(
                "SELECT game FROM names WHERE norm LIKE ? ORDER BY length(norm), game LIMIT ?",
                (norm + "%", limit),
            )
        )
        if len(results) < limit:
            clauses = " AND ".join("norm LIKE ?" for _ in words) or "norm LIKE ?"
            params = [f"%{w}%" for w in words] or [f"%{norm}%"]
            add(
                self.db.execute(
                    f"SELECT game FROM names WHERE {clauses} ORDER BY length(norm), game LIMIT ?",
                    (*params, limit),
                )
            )
        return results[:limit]

    def by_store_id(self, store: str, value: int) -> str | None:
        row = self.db.execute(
            "SELECT game FROM store_ids WHERE store = ? AND id = ? LIMIT 1", (store, value)
        ).fetchone()
        return row[0] if row else None

    def entry(self, name: str) -> dict | None:
        row = self.db.execute("SELECT data FROM games WHERE name = ?", (name,)).fetchone()
        return json.loads(row[0]) if row else None
