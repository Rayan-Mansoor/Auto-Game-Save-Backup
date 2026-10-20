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
    # 4: store IDs read from the game's own files
    """
    ALTER TABLE games ADD COLUMN steam_app_id INTEGER;
    ALTER TABLE games ADD COLUMN gog_id INTEGER;
    """,
    # 5: executables that mean the game is running
    """
    ALTER TABLE games ADD COLUMN executables TEXT NOT NULL DEFAULT '[]';
    """,
    # 6: play sessions, and which session each snapshot was taken in
    """
    CREATE TABLE sessions (
        id INTEGER PRIMARY KEY,
        game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        crashed INTEGER NOT NULL DEFAULT 0
    );
    ALTER TABLE snapshots ADD COLUMN session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL;
    """,
    # 7: per-game minimum gap between checkpoints (NULL uses the global setting)
    """
    ALTER TABLE games ADD COLUMN checkpoint_interval_minutes INTEGER;
    """,
    # 8: health check results for each snapshot
    """
    ALTER TABLE snapshots ADD COLUMN health TEXT;
    ALTER TABLE snapshots ADD COLUMN health_notes TEXT NOT NULL DEFAULT '[]';
    """,
    # 9: snapshots the user wants to keep forever
    """
    ALTER TABLE snapshots ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
    """,
    # 10: whether a cloud service also syncs this game's saves
    """
    ALTER TABLE games ADD COLUMN cloud_sync INTEGER NOT NULL DEFAULT 0;
    """,
]


def apply(connection) -> None:
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[current:], start=current + 1):
        with connection:
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
