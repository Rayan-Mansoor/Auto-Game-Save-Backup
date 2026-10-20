"""Content-addressed object store.

Each distinct file content is stored once, compressed with zstd, at
``objects/<first two hex chars>/<sha256>.zst``. Snapshots refer to contents by digest,
so unchanged files cost nothing extra.
"""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

import zstandard

CHUNK = 1024 * 1024


class CorruptObjectError(Exception):
    """A stored object is missing or its content no longer matches its digest."""


class ObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.tmp = self.root / "tmp"

    def path_for(self, digest: str) -> Path:
        return self.objects / digest[:2] / f"{digest}.zst"

    def exists(self, digest: str) -> bool:
        return self.path_for(digest).exists()

    def put_stream(self, stream: BinaryIO) -> tuple[str, int]:
        """Store the stream's content and return its digest and uncompressed size."""
        self.tmp.mkdir(parents=True, exist_ok=True)
        hasher = hashlib.sha256()
        size = 0
        fd, tmp_name = tempfile.mkstemp(dir=self.tmp, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as raw:
                with zstandard.ZstdCompressor(level=6).stream_writer(raw, closefd=False) as out:
                    while chunk := stream.read(CHUNK):
                        hasher.update(chunk)
                        size += len(chunk)
                        out.write(chunk)
                raw.flush()
                os.fsync(raw.fileno())
            digest = hasher.hexdigest()
            target = self.path_for(digest)
            if target.exists():
                os.unlink(tmp_name)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(tmp_name, target)
            return digest, size
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

    def put_file(self, path: Path) -> tuple[str, int]:
        with open(path, "rb") as fh:
            return self.put_stream(fh)

    def put_bytes(self, data: bytes) -> tuple[str, int]:
        return self.put_stream(io.BytesIO(data))

    def _chunks(self, digest: str) -> Iterator[bytes]:
        """Yield the object's content, raising CorruptObjectError if it does not verify."""
        path = self.path_for(digest)
        if not path.exists():
            raise CorruptObjectError(f"object {digest} is missing")
        hasher = hashlib.sha256()
        try:
            with open(path, "rb") as fh, zstandard.ZstdDecompressor().stream_reader(fh) as reader:
                while chunk := reader.read(CHUNK):
                    hasher.update(chunk)
                    yield chunk
        except zstandard.ZstdError as exc:
            raise CorruptObjectError(f"object {digest} cannot be decompressed: {exc}") from exc
        if hasher.hexdigest() != digest:
            raise CorruptObjectError(f"object {digest} does not match its digest")

    def read_bytes(self, digest: str) -> bytes:
        return b"".join(self._chunks(digest))

    def write_to(self, digest: str, dest: Path) -> None:
        """Write an object's content to ``dest`` atomically, only if it verifies."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as out:
                for chunk in self._chunks(digest):
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp_name, dest)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

    def verify(self, digest: str) -> bool:
        try:
            for _ in self._chunks(digest):
                pass
        except CorruptObjectError:
            return False
        return True

    def digests(self) -> Iterator[str]:
        if not self.objects.exists():
            return
        for path in self.objects.glob("*/*.zst"):
            yield path.name.removesuffix(".zst")

    def delete(self, digest: str) -> None:
        self.path_for(digest).unlink(missing_ok=True)

    def stored_size(self, digest: str) -> int:
        return self.path_for(digest).stat().st_size
