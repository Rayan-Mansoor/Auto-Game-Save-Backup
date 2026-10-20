"""Download the Ludusavi manifest, only when it has changed (ETag)."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from saveix import __version__

MANIFEST_URL = (
    "https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/master/data/manifest.yaml"
)


@dataclass
class Response:
    status: int
    etag: str | None
    body: bytes


Fetch = Callable[[str, dict[str, str]], Response]


def http_fetch(url: str, headers: dict[str, str]) -> Response:
    request = urllib.request.Request(
        url, headers={"User-Agent": f"saveix/{__version__}", **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return Response(response.status, response.headers.get("ETag"), response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return Response(304, exc.headers.get("ETag"), b"")
        raise


def download_manifest(folder: Path, fetch: Fetch = http_fetch, force: bool = False) -> bool:
    """Fetch the manifest into ``folder``; returns whether a new version was saved."""
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / "manifest.yaml"
    etag_file = folder / "manifest.etag"
    headers = {}
    if manifest.exists() and etag_file.exists() and not force:
        headers["If-None-Match"] = etag_file.read_text().strip()
    response = fetch(MANIFEST_URL, headers)
    if response.status == 304:
        return False
    if response.status != 200 or not response.body:
        raise OSError(f"unexpected response {response.status} while downloading the manifest")
    tmp = manifest.with_suffix(".part")
    tmp.write_bytes(response.body)
    os.replace(tmp, manifest)
    if response.etag:
        etag_file.write_text(response.etag)
    else:
        etag_file.unlink(missing_ok=True)
    return True
