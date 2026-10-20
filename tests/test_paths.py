import sys
from pathlib import Path

import pytest

from saveix.core.paths import (
    APPDATA,
    DOCUMENTS,
    HOME,
    INSTALL,
    LOCALAPPDATA,
    FallbackFolders,
    PathContext,
    UnresolvedPlaceholderError,
    WindowsFolders,
    normalize,
    placeholders_in,
)

HOME_DIR = Path("C:/Users/Ana")


def make_context(**kwargs):
    folders = {
        HOME: HOME_DIR,
        APPDATA: HOME_DIR / "AppData" / "Roaming",
        LOCALAPPDATA: HOME_DIR / "AppData" / "Local",
        DOCUMENTS: Path("D:/Docs"),
    }
    return PathContext(folders, **kwargs)


def test_normalize_uses_forward_slashes():
    assert normalize("C:\\Games\\Foo\\") == "C:/Games/Foo"
    assert normalize("C:/") == "C:/"


def test_expand_replaces_placeholders():
    ctx = make_context()
    assert ctx.expand("<appdata>/Game/saves") == "C:/Users/Ana/AppData/Roaming/Game/saves"
    assert ctx.expand("<documents>\\My Games\\*.sav") == "D:/Docs/My Games/*.sav"


def test_unknown_user_id_becomes_wildcard():
    assert make_context().expand("<home>/<userid>/x") == "C:/Users/Ana/*/x"
    assert make_context(user_id="123").expand("<home>/<userid>/x") == "C:/Users/Ana/123/x"


def test_expand_without_install_folder_fails():
    with pytest.raises(UnresolvedPlaceholderError):
        make_context().expand("<install>/save.dat")


def test_expand_with_install_folder():
    ctx = make_context(install=Path("E:/Games/Foo"))
    assert ctx.expand("<install>/save.dat") == "E:/Games/Foo/save.dat"


def test_collapse_prefers_most_specific_placeholder():
    ctx = make_context(install=Path("C:/Users/Ana/AppData/Local/Programs/Foo"))
    assert ctx.collapse("C:\\Users\\Ana\\AppData\\Roaming\\Game") == "<appdata>/Game"
    assert ctx.collapse("C:/Users/Ana/AppData/Local/Programs/Foo/s.dat") == "<install>/s.dat"
    assert ctx.collapse("C:/Users/Ana/notes.txt") == "<home>/notes.txt"


def test_collapse_is_case_insensitive_and_keeps_original_tail():
    assert make_context().collapse("c:/users/ana/AppData/Roaming/MyGame") == "<appdata>/MyGame"


def test_collapse_does_not_match_partial_folder_names():
    assert make_context().collapse("C:/Users/AnaBackup/x") == "C:/Users/AnaBackup/x"


def test_collapse_and_expand_round_trip():
    ctx = make_context()
    for real in ["C:/Users/Ana/AppData/Local/G/s", "D:/Docs/My Games/G", "F:/Elsewhere/save"]:
        assert ctx.expand(ctx.collapse(real)) == real


def test_unknown_angle_brackets_are_left_alone():
    assert make_context().expand("<appdata>/<notaplaceholder>") == (
        "C:/Users/Ana/AppData/Roaming/<notaplaceholder>"
    )
    assert placeholders_in("<install>/<userid>/<nope>") == {INSTALL, "<userid>"}


def test_fallback_folders_are_under_home(tmp_path):
    folders = FallbackFolders(tmp_path).known_folders()
    assert folders[APPDATA] == tmp_path / "AppData" / "Roaming"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows known-folder API")
def test_windows_known_folders_exist():
    folders = WindowsFolders().known_folders()
    assert folders[HOME].is_dir()
    assert folders[APPDATA].is_dir()
    assert folders[DOCUMENTS].is_dir()
