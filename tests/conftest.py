import pytest


@pytest.fixture(autouse=True)
def saveix_home(tmp_path, monkeypatch):
    """Keep every test's config and data inside its own temporary folder."""
    home = tmp_path / "saveix-home"
    monkeypatch.setenv("SAVEIX_HOME", str(home))
    return home
