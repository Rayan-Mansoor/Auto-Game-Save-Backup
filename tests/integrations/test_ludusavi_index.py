import pytest

from saveix.core.providers import ProviderContext
from saveix.integrations.ludusavi.download import Response
from saveix.integrations.ludusavi.index import ManifestIndex, build_index, index_is_current
from saveix.integrations.ludusavi.provider import LudusaviProvider

MANIFEST = """\
Hollow Knight:
  files:
    <home>/AppData/LocalLow/Team Cherry/Hollow Knight/*.dat:
      tags: [save]
      when: [{os: windows}]
  registry:
    HKEY_CURRENT_USER/Software/Team Cherry/Hollow Knight:
      tags: [config]
  steam: {id: 367520}
  gog: {id: 1308320804}
  id: {steamExtra: [598190]}
Hollow Knight - Silksong:
  files:
    <winAppData>/Silksong/save.dat: {tags: [save]}
  steam: {id: 1030300}
"The Witcher 3: Wild Hunt":
  files:
    <winDocuments>/The Witcher 3/gamesaves/*.sav: {tags: [save]}
  steam: {id: 292030}
Witcher 3:
  alias: "The Witcher 3: Wild Hunt"
No Save Info Game:
  steam: {id: 5}
"""


@pytest.fixture
def manifest(tmp_path):
    path = tmp_path / "manifest.yaml"
    path.write_text(MANIFEST)
    return path


def test_build_and_search(manifest, tmp_path):
    index_path = tmp_path / "index.sqlite3"
    assert build_index(manifest, index_path) == 3
    assert index_is_current(manifest, index_path)

    index = ManifestIndex(index_path)
    assert index.search("hollow knight") == ["Hollow Knight", "Hollow Knight - Silksong"]
    assert index.search("SILKSONG") == ["Hollow Knight - Silksong"]
    assert index.search("witcher 3") == ["The Witcher 3: Wild Hunt"]
    assert index.search("wild witcher") == ["The Witcher 3: Wild Hunt"]
    assert index.search("no save info") == []
    assert index.search("") == []
    assert index.by_store_id("steam", 598190) == "Hollow Knight"
    assert index.by_store_id("gog", 1308320804) == "Hollow Knight"
    assert index.by_store_id("steam", 5) is None
    assert index.entry("Hollow Knight")["steam"] == {"id": 367520}
    index.close()


def test_index_goes_stale_when_manifest_changes(manifest, tmp_path):
    import os

    index_path = tmp_path / "index.sqlite3"
    build_index(manifest, index_path)
    stat = manifest.stat()
    os.utime(manifest, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
    assert not index_is_current(manifest, index_path)


def test_provider_search_and_lookup(tmp_path):
    def fetch(url, headers):
        return Response(200, '"x"', MANIFEST.encode())

    provider = LudusaviProvider(ProviderContext(tmp_path), fetch=fetch)
    assert provider.search("hollow") == []
    assert "3 games" in provider.update()

    [match, _] = provider.search("hollow")
    assert (match.name, match.steam_app_id, match.gog_id) == ("Hollow Knight", 367520, 1308320804)
    assert provider.lookup(steam_app_id=292030).name == "The Witcher 3: Wild Hunt"
    assert provider.lookup(gog_id=1308320804).name == "Hollow Knight"
    assert provider.lookup(steam_app_id=1) is None
