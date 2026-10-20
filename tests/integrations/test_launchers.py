import json

import pytest

from saveix.core.providers import ProviderContext, available_providers
from saveix.integrations.launchers import vdf
from saveix.integrations.launchers.provider import LauncherProvider

LIBRARY_VDF = r"""
"libraryfolders"
{
    "0"
    {
        "path"      "{steam}"
        "apps" { "367520" "123" }
    }
    "1"
    {
        "path"      "{other}"  // second drive
    }
}
"""

ACF = """
"AppState"
{
    "appid"     "{appid}"
    "name"      "{name}"
    "installdir"        "{folder}"
}
"""


def test_vdf_parse():
    data = vdf.parse('"a" { "b" "c\\\\d" "e" { "f" "1" } } // note')
    assert data == {"a": {"b": "c\\d", "e": {"f": "1"}}}


@pytest.fixture
def launchers(tmp_path):
    steam = tmp_path / "Steam"
    other = tmp_path / "SteamLibrary"
    (steam / "steamapps").mkdir(parents=True)
    (other / "steamapps").mkdir(parents=True)
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        LIBRARY_VDF.replace("{steam}", str(steam)).replace("{other}", str(other))
    )
    for library, appid, name, folder in [
        (steam, "367520", "Hollow Knight", "Hollow Knight"),
        (other, "292030", "The Witcher 3: Wild Hunt", "The Witcher 3"),
    ]:
        acf = ACF.replace("{appid}", appid).replace("{name}", name).replace("{folder}", folder)
        (library / "steamapps" / f"appmanifest_{appid}.acf").write_text(acf)

    epic = tmp_path / "Manifests"
    epic.mkdir()
    (epic / "a.item").write_text(
        json.dumps(
            {
                "DisplayName": "Celeste",
                "InstallLocation": "D:/Epic/Celeste",
                "AppName": "Salt",
                "LaunchExecutable": "Celeste.exe",
            }
        )
    )
    (epic / "broken.item").write_text("{not json")

    def gog():
        return [
            {
                "id": "1207658924",
                "gameName": "Stardew Valley",
                "path": "C:/GOG/Stardew",
                "exe": "C:/GOG/Stardew/Stardew Valley.exe",
            }
        ]

    return LauncherProvider(ProviderContext(tmp_path / "data"), steam, epic, gog), steam, other


def test_finds_installed_games(launchers):
    provider, steam, other = launchers
    assert provider.update() == "found 4 installed games"
    names = {g.name: g for g in provider.installed()}
    assert names["The Witcher 3: Wild Hunt"].install_dir == str(
        other / "steamapps" / "common" / "The Witcher 3"
    )
    assert names["Celeste"].executable == "Celeste.exe"
    assert names["Stardew Valley"].executable == "Stardew Valley.exe"


def test_search_lookup_details(launchers):
    provider, steam, other = launchers
    [match] = provider.search("hollow")
    assert match.steam_app_id == 367520
    assert provider.lookup(gog_id=1207658924).name == "Stardew Valley"
    assert provider.lookup(steam_app_id=1) is None

    details = provider.details(match)
    assert details.install_dir == str(steam / "steamapps" / "common" / "Hollow Knight")
    assert details.sources[0].path.endswith("/userdata/<userid>/367520/remote")
    celeste = provider.details(provider.search("celeste")[0])
    assert celeste.executables == ["Celeste.exe"] and celeste.sources == []


def test_registered_and_tolerates_missing_launchers(tmp_path):
    assert "launchers" in available_providers()
    empty = LauncherProvider(
        ProviderContext(tmp_path), tmp_path / "none", tmp_path / "none", lambda: []
    )
    assert empty.installed() == []
