import sys
import uuid

import pytest
from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.backup import BackupEngine
from saveix.core.catalog import Catalog
from saveix.core.models import Source, SourceKind, Trigger
from saveix.core.restore import Action, Restorer
from saveix.core.sources.registry import (
    MemoryRegistry,
    RegistryError,
    WindowsRegistry,
    is_registry_path,
    normalize_key,
)
from saveix.core.sources.resolve import scan_source
from saveix.core.store import ObjectStore

KEY = "HKCU/Software/Team Cherry/Hollow Knight"
runner = CliRunner()


def tree(level):
    return {
        "values": {"level": [4, level], "blob": [3, {"hex": "00ff"}]},
        "keys": {"Sub": {"values": {"x": [1, "y"]}, "keys": {}}},
    }


def test_normalize_key():
    assert normalize_key("HKEY_CURRENT_USER\\Software\\A\\B") == "HKCU/Software/A/B"
    assert is_registry_path("HKCU\\Software\\A") and not is_registry_path("C:/Games")
    with pytest.raises(RegistryError):
        normalize_key("HKEY_LOCAL_MACHINE/Software/A")
    with pytest.raises(RegistryError):
        normalize_key("HKCU/Software")


def test_scan_registry_source(context):
    registry = MemoryRegistry()
    source = Source(SourceKind.REGISTRY, KEY, id=1)
    assert scan_source(source, context, registry).files == []

    registry.write_tree(KEY, tree(1))
    found = scan_source(source, context, registry).files
    assert [f.template for f in found] == [f"<registry>/{KEY}"]


def test_registry_backup_and_restore(tmp_path, context):
    registry = MemoryRegistry()
    registry.write_tree(KEY, tree(1))
    with Catalog(tmp_path / "c.sqlite3") as catalog:
        game = catalog.add_game("Hollow Knight")
        catalog.add_source(game, Source(SourceKind.REGISTRY, KEY))
        store = ObjectStore(tmp_path / "backups")
        engine = BackupEngine(catalog, store, clock=lambda: "t", registry=registry)
        restorer = Restorer(catalog, store, engine)

        first = engine.backup(game, context, Trigger.MANUAL).snapshot
        assert engine.backup(game, context, Trigger.MANUAL).unchanged
        registry.write_tree(KEY, tree(2))
        assert engine.backup(game, context, Trigger.MANUAL).changed_files == 1

        plan = restorer.plan(game, first, context)
        assert [f.action for f in plan.files] == [Action.WRITE]
        restorer.execute(plan, context)
        assert registry.read_tree(KEY) == tree(1)
        assert not restorer.plan(game, first, context).has_changes


def test_registry_unavailable_off_windows(context, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("only for systems without a registry")
    scan = scan_source(Source(SourceKind.REGISTRY, KEY, id=1), context)
    assert "only work on Windows" in scan.error


def test_add_registry_source_command(fake_home):
    runner.invoke(app, ["game", "add", "HK"])
    result = runner.invoke(
        app, ["source", "add", "HK", "HKEY_CURRENT_USER\\Software\\Team Cherry\\Hollow Knight"]
    )
    assert result.exit_code == 0, result.output
    assert f"registry save   {KEY}" in runner.invoke(app, ["game", "show", "HK"]).output
    assert runner.invoke(app, ["source", "add", "HK", "HKLM\\Software\\X\\Y"]).exit_code == 1


@pytest.mark.skipif(sys.platform != "win32", reason="real Windows registry")
def test_windows_registry_round_trip():
    key = f"HKCU/Software/saveix-test-{uuid.uuid4().hex}"
    registry = WindowsRegistry()
    try:
        registry.write_tree(key, tree(7))
        assert registry.read_tree(key) == tree(7)
        registry.write_tree(key, tree(8))
        assert registry.read_tree(key) == tree(8)
    finally:
        registry.delete_tree(key)
    assert registry.read_tree(key) is None
