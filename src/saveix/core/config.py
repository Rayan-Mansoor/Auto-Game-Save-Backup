"""Application settings and data directories."""

from __future__ import annotations

import dataclasses
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs
import tomli_w

APP_NAME = "saveix"
HOME_ENV = "SAVEIX_HOME"


@dataclass(frozen=True)
class AppDirs:
    """Where saveix keeps its configuration and its own data."""

    config_dir: Path
    data_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @classmethod
    def default(cls) -> AppDirs:
        home = os.environ.get(HOME_ENV)
        if home:
            root = Path(home)
            return cls(config_dir=root, data_dir=root / "data")
        return cls(
            config_dir=Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)),
            data_dir=Path(platformdirs.user_data_dir(APP_NAME, appauthor=False)),
        )


@dataclass
class Settings:
    """User-editable settings stored in config.toml."""

    backup_root: str = ""
    quiet_period_seconds: int = 10
    checkpoint_interval_minutes: int = 10
    recent_sessions_kept: int = 3
    keep_all_snapshots: bool = False
    max_snapshots_per_game: int = 0
    """0 means no limit."""
    max_storage_mb: int = 0
    """Limit for the whole backup store; 0 means no limit."""
    providers: list[str] = field(default_factory=list)

    @classmethod
    def keys(cls) -> list[str]:
        return [f.name for f in dataclasses.fields(cls)]

    def set(self, key: str, raw: str) -> None:
        """Set a setting from its string form, converting to the field's type."""
        if key not in self.keys():
            raise KeyError(key)
        current = getattr(self, key)
        if isinstance(current, bool):
            value: object = raw.strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(current, int):
            value = int(raw)
            if value < 0:
                raise ValueError(f"{key} must not be negative")
        elif isinstance(current, list):
            value = [item.strip() for item in raw.split(",") if item.strip()]
        else:
            value = raw
        setattr(self, key, value)


class Config:
    """Loads and saves settings for a set of app directories."""

    def __init__(self, dirs: AppDirs | None = None) -> None:
        self.dirs = dirs or AppDirs.default()
        self.settings = self._load()

    @property
    def backup_root(self) -> Path:
        if self.settings.backup_root:
            return Path(self.settings.backup_root).expanduser()
        return self.dirs.data_dir / "backups"

    @property
    def catalog_path(self) -> Path:
        return self.dirs.data_dir / "catalog.sqlite3"

    def _load(self) -> Settings:
        path = self.dirs.config_file
        if not path.exists():
            return Settings()
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
        known = {k: v for k, v in raw.items() if k in Settings.keys()}
        return Settings(**known)

    def save(self) -> None:
        self.dirs.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dirs.config_file.with_suffix(".tmp")
        tmp.write_bytes(tomli_w.dumps(dataclasses.asdict(self.settings)).encode())
        os.replace(tmp, self.dirs.config_file)
