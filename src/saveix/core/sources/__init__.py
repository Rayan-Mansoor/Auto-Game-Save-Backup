"""Save sources: checking new ones and resolving them into files."""

from __future__ import annotations

import re
from pathlib import Path

from saveix.core.models import MANUAL, Source, SourceKind, SourceRole
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


def make_source(
    path: str,
    context: PathContext,
    kind: SourceKind | None = None,
    role: SourceRole = SourceRole.SAVE,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    force: bool = False,
    origin: str = MANUAL,
) -> Source:
    """Build a source from a path the user gave: a real path, template or registry key.

    Raises SourceError when the path cannot be used or looks too broad (unless forced).
    """
    from saveix.core.paths import UnresolvedPlaceholderError
    from saveix.core.sources.registry import RegistryError, is_registry_path, normalize_key

    if kind is SourceKind.REGISTRY or (kind is None and is_registry_path(path)):
        kind = SourceKind.REGISTRY
        try:
            template = normalize_key(path)
        except RegistryError as exc:
            raise SourceError(str(exc)) from None
    else:
        template = to_template(path, context)
        if kind is None:
            try:
                kind = guess_kind(context.expand(template))
            except UnresolvedPlaceholderError as exc:
                raise SourceError(str(exc)) from None
    problem = breadth_problem(template)
    if problem and not force:
        raise SourceError(f"{problem}. Use --force to add it anyway.")
    return Source(kind, template, role, list(include or []), list(exclude or []), origin)
