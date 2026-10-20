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
    # 2: snapshots and the file contents each one captured
    """
    CREATE TABLE snapshots (
        id INTEGER PRIMARY KEY,
        game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        trigger TEXT NOT NULL,
        label TEXT,
        note TEXT,
        file_count INTEGER NOT NULL,
        total_size INTEGER NOT NULL,
        fingerprint TEXT NOT NULL
    );
    CREATE INDEX snapshots_by_game ON snapshots (game_id, id);
    CREATE TABLE snapshot_files (
        snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
        source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
        source_path TEXT NOT NULL,
        template TEXT NOT NULL,
        digest TEXT NOT NULL,
        size INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL,
        PRIMARY KEY (snapshot_id, template)
    );
    CREATE INDEX snapshot_files_by_digest ON snapshot_files (digest);
    """,
    # 3: where a game is installed on this PC, for <install> paths
    """
    ALTER TABLE games ADD COLUMN install_dir TEXT;
    """,
]


def apply(connection) -> None:
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[current:], start=current + 1):
        with connection:
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
