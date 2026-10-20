"""Health checks that flag snapshots whose saves look damaged.

Each new snapshot is compared with the game's previous one. Only files that changed
are examined: general warning signs first, then checks for well-known file formats.
"""

from __future__ import annotations

import gzip
import io
import json
import sqlite3
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from xml.etree import ElementTree

from saveix.core.models import SnapshotFile
from saveix.core.sources.registry import key_from_template

MAX_FORMAT_CHECK_SIZE = 64 * 1024 * 1024
SIZE_DROP_RATIO = 0.25
SIZE_DROP_MIN = 1024

MAGIC = {
    b"GVAS": "Unreal Engine save",
    b"SQLi": "SQLite database",
    b"PK\x03\x04": "zip archive",
    b"\x1f\x8b": "gzip file",
}


class Health(StrEnum):
    OK = "ok"
    SUSPICIOUS = "suspicious"


@dataclass(frozen=True)
class Finding:
    template: str
    message: str


def _magic(data: bytes) -> str | None:
    for prefix, name in MAGIC.items():
        if data.startswith(prefix):
            return name
    return None


def _format_problem(name: str, data: bytes) -> str | None:
    lower = name.lower()
    if len(data) > MAX_FORMAT_CHECK_SIZE:
        return None
    try:
        if lower.endswith(".json"):
            json.loads(data.decode("utf-8-sig"))
        elif lower.endswith(".xml"):
            ElementTree.fromstring(data)
        elif data.startswith(b"SQLite format 3\x00"):
            return _sqlite_problem(data)
        elif data.startswith(b"PK\x03\x04"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                bad = archive.testzip()
            if bad:
                return f"zip entry {bad} is damaged"
        elif data.startswith(b"\x1f\x8b"):
            gzip.decompress(data)
    except (ValueError, ElementTree.ParseError, zipfile.BadZipFile, OSError, EOFError) as exc:
        return f"not a valid {Path(lower).suffix.lstrip('.') or 'file'}: {exc}"
    return None


def _sqlite_problem(data: bytes) -> str | None:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "check.sqlite3"
        path.write_bytes(data)
        db = sqlite3.connect(path)
        try:
            result = db.execute("PRAGMA quick_check").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            return f"SQLite database is damaged: {exc}"
        finally:
            db.close()
    return None if result == "ok" else f"SQLite database is damaged: {result}"


def check_snapshot(
    files: list[SnapshotFile],
    previous: list[SnapshotFile] | None,
    read: Callable[[str], bytes],
    crashed: bool = False,
) -> list[Finding]:
    """Look for signs that a snapshot captured damaged saves."""
    findings: list[Finding] = []
    before = {f.template: f for f in previous or []}
    if crashed:
        findings.append(Finding("", "the game crashed just before these saves were taken"))

    for entry in files:
        old = before.get(entry.template)
        if old and old.digest == entry.digest:
            continue
        if key_from_template(entry.template):
            continue
        name = entry.template
        if entry.size == 0:
            if old and old.size > 0:
                findings.append(Finding(name, "file became empty"))
            continue
        if old and old.size >= SIZE_DROP_MIN and entry.size < old.size * SIZE_DROP_RATIO:
            findings.append(Finding(name, f"file shrank from {old.size} to {entry.size} bytes"))
        data = read(entry.digest) if entry.size <= MAX_FORMAT_CHECK_SIZE else None
        if data is None:
            continue
        if data.count(0) == len(data):
            findings.append(Finding(name, "file contains only zero bytes"))
            continue
        if old:
            old_kind = _magic(read(old.digest)[:16])
            if old_kind and _magic(data[:16]) != old_kind:
                findings.append(Finding(name, f"file is no longer a valid {old_kind}"))
                continue
        problem = _format_problem(name, data)
        if problem:
            findings.append(Finding(name, problem))

    if previous:
        now = {f.template for f in files}
        gone = [t for t in before if t not in now and not key_from_template(t)]
        total = sum(1 for t in before if not key_from_template(t))
        if total >= 2 and len(gone) * 2 > total:
            findings.append(Finding("", f"{len(gone)} of {total} save files disappeared"))
    return findings
