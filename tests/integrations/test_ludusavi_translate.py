from saveix.core.models import SourceKind, SourceRole
from saveix.core.providers import GameMatch
from saveix.integrations.ludusavi.translate import translate_entry, translate_path


def test_translate_paths():
    assert translate_path("<home>/AppData/LocalLow/TC/HK/*.dat", None) == "<locallow>/TC/HK/*.dat"
    assert translate_path("<winAppData>/G/saves", None) == "<appdata>/G/saves"
    assert translate_path("<winDocuments>/My Games/G", None) == "<documents>/My Games/G"
    assert translate_path("<base>/SaveData", None) == "<install>/SaveData"
    assert translate_path("<winDocuments>/R/<storeUserId>", None) == "<documents>/R/<userid>"
    assert translate_path("<root>/userdata/<storeUserId>/525480/remote/savedata", 525480) == (
        "<steamremote>/savedata"
    )
    assert translate_path("<root>/userdata/<storeUserId>/1/remote", 525480) is None
    assert translate_path("<xdgConfig>/g", None) is None
    assert translate_path("<winDir>/g.ini", None) is None
    assert translate_path("<home>/AppData/Local/<storeGameId>/s", 7) == "<localappdata>/7/s"
    assert translate_path("<home>/AppData/Local/<storeGameId>/s", None) is None


def test_translate_entry():
    entry = {
        "files": {
            "<home>/AppData/LocalLow/Team Cherry/Hollow Knight/*.dat": {
                "tags": ["save"],
                "when": [{"os": "windows"}],
            },
            "<base>/hollow_knight_Data/Config.ini": {
                "tags": ["config"],
                "when": [{"os": "windows"}, {"os": "linux"}],
            },
            "<home>/Library/Application Support/x": {"tags": ["save"], "when": [{"os": "mac"}]},
        },
        "registry": {
            "HKEY_CURRENT_USER/Software/Team Cherry/Hollow Knight": {"tags": ["config"]},
            "HKEY_LOCAL_MACHINE/Software/X/Y": {"tags": ["save"]},
        },
        "launch": {
            "<base>/hollow_knight.exe": [{"when": [{"os": "windows", "store": "steam"}]}],
            "<base>/hollow_knight.x86_64": [{"when": [{"os": "linux"}]}],
        },
        "steam": {"id": 367520},
        "cloud": {"steam": True},
    }
    details = translate_entry(GameMatch("ludusavi", "Hollow Knight", "Hollow Knight"), entry)
    assert [(c.kind, c.path, c.role) for c in details.sources] == [
        (SourceKind.GLOB, "<locallow>/Team Cherry/Hollow Knight/*.dat", SourceRole.SAVE),
        (SourceKind.GLOB, "<install>/hollow_knight_Data/Config.ini", SourceRole.CONFIG),
        (SourceKind.REGISTRY, "HKCU/Software/Team Cherry/Hollow Knight", SourceRole.CONFIG),
    ]
    assert details.executables == ["hollow_knight.exe"]
    assert details.cloud_sync is True
