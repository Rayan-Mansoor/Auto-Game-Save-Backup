"""Catalog schema, built up by numbered migrations tracked in PRAGMA user_version."""

MIGRATIONS: list[str] = [
    # 1: games and their save sources
    """
    CREATE TABLE games (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    );
    CREATE TABLE sources (
        id INTEGER PRIMARY KEY,
        game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        path TEXT NOT NULL,
        role TEXT NOT NULL,
        include TEXT NOT NULL DEFAULT '[]',
        exclude TEXT NOT NULL DEFAULT '[]',
        origin TEXT NOT NULL,
        UNIQUE (game_id, kind, path)
    );
    """,
]


def apply(connection) -> None:
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[current:], start=current + 1):
        with connection:
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
