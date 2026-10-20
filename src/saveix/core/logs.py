"""Log to a rotating file in saveix's data folder (and optionally the console)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from saveix.core.config import Config

FORMAT = "%(asctime)s %(levelname)s %(message)s"


def log_file(config: Config) -> Path:
    return config.dirs.data_dir / "logs" / "saveix.log"


def setup_logging(config: Config, console: bool = False) -> Path:
    path = log_file(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        if getattr(handler, "_saveix", False):
            root.removeHandler(handler)
            handler.close()
    handlers: list[logging.Handler] = [
        RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    ]
    handlers[0].setFormatter(logging.Formatter(FORMAT))
    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
        handlers.append(stream)
    for handler in handlers:
        handler._saveix = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    return path
