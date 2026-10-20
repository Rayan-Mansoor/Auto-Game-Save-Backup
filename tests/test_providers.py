import ast
import pathlib

import pytest
from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.providers import Provider, load_providers
from tests import fake_provider

runner = CliRunner()
SRC = pathlib.Path(__file__).parent.parent / "src" / "saveix"


@pytest.fixture
def fake_installed(monkeypatch):
    def available():
        return {"fake": lambda: fake_provider.factory, "broken": lambda: 1 / 0}

    monkeypatch.setattr("saveix.core.providers.available_providers", available)
    monkeypatch.setattr("saveix.cli.providers.available_providers", available)


def test_core_never_imports_integrations():
    for path in (SRC / "core").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                continue
            for name in names:
                assert not name.startswith("saveix.integrations"), f"{path} imports {name}"


def test_load_only_enabled_and_skip_broken(fake_installed, tmp_path):
    providers = load_providers(["fake", "broken", "missing"], tmp_path)
    assert [p.name for p in providers] == ["fake"]
    assert isinstance(providers[0], Provider)
    assert providers[0].context.data_dir == tmp_path / "providers" / "fake"


def test_provider_commands(fake_installed, fake_home):
    assert "fake  (disabled)" in runner.invoke(app, ["providers", "list"]).output
    assert runner.invoke(app, ["search", "knight"]).exit_code == 1
    assert runner.invoke(app, ["providers", "enable", "nope"]).exit_code == 1

    assert runner.invoke(app, ["providers", "enable", "fake"]).exit_code == 0
    assert "fake  (enabled)" in runner.invoke(app, ["providers", "list"]).output
    assert "fake: up to date" in runner.invoke(app, ["providers", "update"]).output
    result = runner.invoke(app, ["search", "witcher"])
    assert "[fake] The Witcher 3  (Steam 292030, GOG 1495134320)" in result.output
    assert "No matches." in runner.invoke(app, ["search", "zelda"]).output

    assert runner.invoke(app, ["providers", "disable", "fake"]).exit_code == 0
    assert runner.invoke(app, ["providers", "disable", "fake"]).exit_code == 1


def test_no_providers_installed(monkeypatch):
    monkeypatch.setattr("saveix.cli.providers.available_providers", lambda: {})
    assert "No providers are installed." in runner.invoke(app, ["providers", "list"]).output
