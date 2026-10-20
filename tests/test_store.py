import hashlib
import os

import pytest

from saveix.core.store import CorruptObjectError, ObjectStore


@pytest.fixture
def store(tmp_path):
    return ObjectStore(tmp_path / "backups")


def test_put_and_read_round_trip(store):
    data = b"save data " * 1000
    digest, size = store.put_bytes(data)

    assert digest == hashlib.sha256(data).hexdigest()
    assert size == len(data)
    assert store.read_bytes(digest) == data
    assert store.stored_size(digest) < size


def test_same_content_is_stored_once(store, tmp_path):
    a = tmp_path / "a.sav"
    b = tmp_path / "b.sav"
    a.write_bytes(b"same")
    b.write_bytes(b"same")

    assert store.put_file(a) == store.put_file(b)
    assert len(list(store.digests())) == 1
    assert list(store.tmp.iterdir()) == []


def test_large_file_streams(store, tmp_path):
    big = tmp_path / "big.bin"
    big.write_bytes(os.urandom(3 * 1024 * 1024 + 7))
    digest, size = store.put_file(big)
    dest = tmp_path / "restored" / "big.bin"
    store.write_to(digest, dest)
    assert dest.read_bytes() == big.read_bytes()


def test_tampered_object_is_detected(store, tmp_path):
    digest, _ = store.put_bytes(b"original")
    other, _ = store.put_bytes(b"different")
    os.replace(store.path_for(other), store.path_for(digest))

    assert not store.verify(digest)
    with pytest.raises(CorruptObjectError):
        store.read_bytes(digest)


def test_corrupt_object_never_overwrites_destination(store, tmp_path):
    digest, _ = store.put_bytes(b"original")
    store.path_for(digest).write_bytes(b"garbage")
    dest = tmp_path / "save.dat"
    dest.write_bytes(b"current")

    with pytest.raises(CorruptObjectError):
        store.write_to(digest, dest)
    assert dest.read_bytes() == b"current"
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".save")] == []


def test_missing_object(store):
    assert not store.verify("ab" * 32)
    with pytest.raises(CorruptObjectError):
        store.read_bytes("ab" * 32)


def test_delete(store):
    digest, _ = store.put_bytes(b"x")
    store.delete(digest)
    assert not store.exists(digest)
