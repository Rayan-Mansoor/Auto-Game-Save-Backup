import pytest

from saveix.core.paths import FallbackFolders, PathContext


@pytest.fixture(autouse=True)
def saveix_home(tmp_path, monkeypatch):
    """Keep every test's config and data inside its own temporary folder."""
    home = tmp_path / "saveix-home"
    monkeypatch.setenv("SAVEIX_HOME", str(home))
    return home


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Point placeholder resolution at a fake Windows-style home folder."""
    home = tmp_path / "home"
    folders = FallbackFolders(home)
    monkeypatch.setattr("saveix.core.paths.system_folders", lambda: folders)
    for folder in folders.known_folders().values():
        if str(folder).startswith(str(home)):
            folder.mkdir(parents=True, exist_ok=True)
    return home


@pytest.fixture
def context(fake_home):
    return PathContext.for_system()
