"""Save sources: checking new ones and resolving them into files."""

from __future__ import annotations

import re
from pathlib import Path

from saveix.core.models import SourceKind
from saveix.core.paths import ALL_PLACEHOLDERS, PathContext, normalize

GLOB_CHARS = set("*?[")


class SourceError(ValueError):
    pass


def has_glob(path: str) -> bool:
    return any(char in GLOB_CHARS for char in path)


def guess_kind(real_path: str) -> SourceKind:
    """Infer the kind of a manually given path."""
    if has_glob(real_path):
        return SourceKind.GLOB
    path = Path(real_path)
    if path.is_dir():
        return SourceKind.FOLDER
    if path.is_file():
        return SourceKind.FILE
    raise SourceError(f"'{real_path}' does not exist; pass --kind to add it anyway")


def to_template(path: str, context: PathContext) -> str:
    """Store a path as a template unless it already is one."""
    if any(name in path for name in ALL_PLACEHOLDERS):
        return normalize(path)
    return context.collapse(Path(path).expanduser().absolute())


def breadth_problem(template: str) -> str | None:
    """Explain why a source path is too broad to be a game's save location, if it is."""
    text = normalize(template).rstrip("/")
    if text in ALL_PLACEHOLDERS:
        return f"'{template}' is a whole system folder, not one game's save location"
    if text in ("", "/") or re.fullmatch(r"[A-Za-z]:/?", text):
        return f"'{template}' is a whole drive"
    if text.startswith("*") or text in {f"{name}/*" for name in ALL_PLACEHOLDERS}:
        return f"'{template}' matches far too much"
    return None
