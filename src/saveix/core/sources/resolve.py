"""Turn a game's save sources into the concrete files they currently cover."""

from __future__ import annotations

import dataclasses
import fnmatch
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path

from saveix.core.models import Game, Source, SourceKind
from saveix.core.paths import PathContext, UnresolvedPlaceholderError, normalize
from saveix.core.sources import registry as reg


@dataclass(frozen=True)
class FoundFile:
    source_id: int
    path: Path | None
    """The file on disk; None for a registry key."""
    size: int
    mtime_ns: int
    template: str
    """Where the file lives, as a portable template; the key used for restoring."""
    data: bytes | None = None
    """The captured content of a registry key."""


@dataclass
class SourceScan:
    source: Source
    files: list[FoundFile] = field(default_factory=list)
    error: str | None = None

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)


def matches(pattern: str, relative: str) -> bool:
    """Match a filter pattern against a path relative to the source.

    Patterns without a slash match the file name at any depth; patterns with a slash
    match the whole relative path.
    """
    pattern = normalize(pattern)
    if "/" not in pattern:
        return fnmatch.fnmatch(relative.rsplit("/", 1)[-1], pattern)
    return fnmatch.fnmatch(relative, pattern)


def _wanted(source: Source, relative: str) -> bool:
    if source.include and not any(matches(p, relative) for p in source.include):
        return False
    return not any(matches(p, relative) for p in source.exclude)


def _files_under(root: Path) -> list[tuple[Path, str]]:
    if root.is_file():
        return [(root, root.name)]
    found = []
    for folder, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            path = Path(folder) / name
            found.append((path, normalize(path.relative_to(root))))
    return found


_USER_SENTINEL = "\x00userid\x00"


def glob_pattern(source: Source, context: PathContext) -> str:
    """The glob that finds a source's paths.

    Only glob sources use wildcards from their template; folder and file paths are
    literal except for an unknown ``<userid>``, which matches every user's folder.
    """
    if source.kind is SourceKind.GLOB:
        return context.expand(source.path, escape=True)
    marked = dataclasses.replace(context, user_id=_USER_SENTINEL).expand(source.path)
    user = glob.escape(context.user_id) if context.user_id else "*"
    return glob.escape(marked).replace(_USER_SENTINEL, user)


def scan_registry(source: Source, registry: reg.RegistryBackend) -> SourceScan:
    result = SourceScan(source)
    try:
        tree = registry.read_tree(source.path)
    except (reg.RegistryError, OSError) as exc:
        result.error = str(exc)
        return result
    if tree is not None:
        data = reg.serialize(tree)
        template = reg.template_for(source.path)
        result.files.append(FoundFile(source.id, None, len(data), 0, template, data=data))
    return result


def scan_source(
    source: Source, context: PathContext, registry: reg.RegistryBackend | None = None
) -> SourceScan:
    if source.kind is SourceKind.REGISTRY:
        return scan_registry(source, registry or reg.system_registry())
    result = SourceScan(source)
    try:
        pattern = glob_pattern(source, context)
    except UnresolvedPlaceholderError as exc:
        result.error = str(exc)
        return result

    seen: set[Path] = set()
    for match in sorted(glob.glob(pattern, recursive=True, include_hidden=True)):
        for path, relative in _files_under(Path(match)):
            if path in seen or not _wanted(source, relative):
                continue
            seen.add(path)
            try:
                stat = path.stat()
            except OSError:
                continue
            result.files.append(
                FoundFile(source.id, path, stat.st_size, stat.st_mtime_ns, context.collapse(path))
            )
    return result


def scan_game(
    game: Game, context: PathContext, registry: reg.RegistryBackend | None = None
) -> list[SourceScan]:
    return [scan_source(source, context, registry) for source in game.sources]
