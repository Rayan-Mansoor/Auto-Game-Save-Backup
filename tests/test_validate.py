import gzip
import hashlib
import io
import json
import sqlite3
import zipfile

import pytest
from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.models import SnapshotFile
from saveix.core.validate import check_snapshot

runner = CliRunner()


class Blobs:
    def __init__(self):
        self.data = {}

    def entry(self, template, data):
        digest = hashlib.sha256(data).hexdigest()
        self.data[digest] = data
        return SnapshotFile(1, "<appdata>/G", template, digest, len(data), 0)

    def read(self, digest):
        return self.data[digest]


@pytest.fixture
def blobs():
    return Blobs()


def messages(findings):
    return [f.message for f in findings]


def sqlite_bytes(tmp_path, damage=False):
    path = tmp_path / f"db-{damage}.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE t (x)")
        db.executemany("INSERT INTO t VALUES (?)", [("x" * 500,)] * 50)
    db.close()
    data = bytearray(path.read_bytes())
    if damage:
        data[100:4096] = b"\xff" * (4096 - 100)
    return bytes(data)


def test_healthy_changes_have_no_findings(blobs):
    old = [blobs.entry("a.json", b'{"level": 1}'), blobs.entry("b.sav", b"x" * 2000)]
    new = [blobs.entry("a.json", b'{"level": 2}'), blobs.entry("b.sav", b"y" * 1900)]
    assert check_snapshot(new, old, blobs.read) == []
    assert check_snapshot(old, None, blobs.read) == []


def test_general_warning_signs(blobs):
    old = [
        blobs.entry("empty.sav", b"data"),
        blobs.entry("zeros.sav", b"data"),
        blobs.entry("shrunk.sav", b"x" * 4000),
    ]
    new = [
        blobs.entry("empty.sav", b""),
        blobs.entry("zeros.sav", b"\0" * 64),
        blobs.entry("shrunk.sav", b"x" * 100),
    ]
    assert messages(check_snapshot(new, old, blobs.read)) == [
        "file became empty",
        "file contains only zero bytes",
        "file shrank from 4000 to 100 bytes",
    ]


def test_missing_files_and_crash(blobs):
    old = [blobs.entry(f"slot{i}.sav", b"x") for i in range(4)]
    new = old[:1]
    assert messages(check_snapshot(new, old, blobs.read, crashed=True)) == [
        "the game crashed just before these saves were taken",
        "3 of 4 save files disappeared",
    ]
    # Deleting one save slot out of four is normal.
    assert check_snapshot(old[:3], old, blobs.read) == []


def test_format_checks(blobs, tmp_path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("inner", "x" * 100)
    good_zip = archive.getvalue()
    new = [
        blobs.entry("a.json", b'{"level": '),
        blobs.entry("b.xml", b"<save><unclosed></save>"),
        blobs.entry("c.dat", good_zip[:-30]),
        blobs.entry("d.gz", gzip.compress(b"x" * 100)[:-4]),
        blobs.entry("e.db", sqlite_bytes(tmp_path, damage=True)),
        blobs.entry("ok.db", sqlite_bytes(tmp_path)),
        blobs.entry("ok.zip", good_zip),
    ]
    found = {f.template for f in check_snapshot(new, None, blobs.read)}
    assert found == {"a.json", "b.xml", "c.dat", "d.gz", "e.db"}


def test_lost_file_format_signature(blobs):
    old = [blobs.entry("slot.sav", b"GVAS" + b"\1" * 100)]
    new = [blobs.entry("slot.sav", b"\x07garbage" + b"\2" * 100)]
    assert messages(check_snapshot(new, old, blobs.read)) == [
        "file is no longer a valid Unreal Engine save"
    ]


def test_suspicious_snapshot_shows_in_timeline(fake_home):
    saves = fake_home / "AppData" / "Roaming" / "G"
    saves.mkdir(parents=True)
    (saves / "save.json").write_text(json.dumps({"level": 1}))
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", str(saves)])
    runner.invoke(app, ["backup", "G"])
    (saves / "save.json").write_text('{"level": 2, "inventory": [')
    runner.invoke(app, ["backup", "G"])

    output = runner.invoke(app, ["timeline", "G"]).output.splitlines()
    assert output[0].startswith("⚠ #2")
    assert "save.json: not a valid json" in output[1]
    assert output[2].startswith("✓ #1")
    result = runner.invoke(app, ["check", "2"])
    assert "looks damaged" in result.output
    assert "looks healthy" in runner.invoke(app, ["check", "1"]).output
