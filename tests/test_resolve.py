from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.models import Game, Source, SourceKind
from saveix.core.sources.resolve import matches, scan_source

runner = CliRunner()


def write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def templates(scan):
    return [f.template for f in scan.files]


def test_folder_source_is_recursive(fake_home, context):
    root = fake_home / "AppData" / "Roaming" / "G"
    write(root / "slot1.sav")
    write(root / "sub" / "slot2.sav")
    write(root / ".hidden")

    scan = scan_source(Source(SourceKind.FOLDER, "<appdata>/G", id=1), context)
    assert templates(scan) == [
        "<appdata>/G/.hidden",
        "<appdata>/G/slot1.sav",
        "<appdata>/G/sub/slot2.sav",
    ]


def test_include_and_exclude(fake_home, context):
    root = fake_home / "AppData" / "Roaming" / "G"
    write(root / "a.sav")
    write(root / "log.txt")
    write(root / "Cache" / "b.sav")
    source = Source(SourceKind.FOLDER, "<appdata>/G", include=["*.sav"], exclude=["Cache/*"], id=1)
    assert templates(scan_source(source, context)) == ["<appdata>/G/a.sav"]


def test_glob_source(fake_home, context):
    root = fake_home / "Documents" / "W3" / "gamesaves"
    write(root / "a.sav")
    write(root / "a.png")
    scan = scan_source(Source(SourceKind.GLOB, "<documents>/W3/gamesaves/*.sav", id=1), context)
    assert templates(scan) == ["<documents>/W3/gamesaves/a.sav"]


def test_user_id_wildcard_covers_every_profile(fake_home, context):
    write(fake_home / "Documents" / "R" / "Profiles" / "111" / "s")
    write(fake_home / "Documents" / "R" / "Profiles" / "222" / "s")
    scan = scan_source(Source(SourceKind.FOLDER, "<documents>/R/Profiles/<userid>", id=1), context)
    assert len(scan.files) == 2


def test_glob_characters_in_real_folder_names_are_literal(fake_home, context):
    write(fake_home / "AppData" / "Roaming" / "G [EU]" / "s.dat")
    scan = scan_source(Source(SourceKind.FOLDER, "<appdata>/G [EU]", id=1), context)
    assert templates(scan) == ["<appdata>/G [EU]/s.dat"]


def test_file_source_and_missing_paths(fake_home, context):
    write(fake_home / "AppData" / "Local" / "G" / "settings.ini")
    assert len(scan_source(Source(SourceKind.FILE, "<localappdata>/G/settings.ini"), context).files)
    missing = scan_source(Source(SourceKind.FOLDER, "<localappdata>/Nope"), context)
    assert missing.files == [] and missing.error is None


def test_unresolved_install_folder_is_an_error(context):
    scan = scan_source(Source(SourceKind.FOLDER, "<install>/saves"), context)
    assert "<install>" in scan.error


def test_matches():
    assert matches("*.sav", "deep/dir/x.sav")
    assert not matches("Cache/*", "Other/x")
    assert matches("Cache/*", "Cache/a/b")


def test_scan_command(fake_home):
    write(fake_home / "AppData" / "Roaming" / "G" / "s.sav", "12345")
    runner.invoke(app, ["game", "add", "G"])
    runner.invoke(app, ["source", "add", "G", "<appdata>/G", "--kind", "folder"])
    runner.invoke(app, ["source", "add", "G", "<install>/x", "--kind", "folder"])

    result = runner.invoke(app, ["scan", "G", "--files"])
    assert result.exit_code == 0, result.output
    assert "[1] <appdata>/G: 1 files, 5 B" in result.output
    assert "<appdata>/G/s.sav" in result.output
    assert "[2] <install>/x: error" in result.output


def test_scan_game_covers_every_source(fake_home, context):
    from saveix.core.sources.resolve import scan_game

    write(fake_home / "AppData" / "Roaming" / "G" / "s")
    write(fake_home / "Documents" / "G" / "c")
    game = Game(
        "G",
        sources=[
            Source(SourceKind.FOLDER, "<appdata>/G"),
            Source(SourceKind.FOLDER, "<documents>/G"),
        ],
    )
    assert [len(s.files) for s in scan_game(game, context)] == [1, 1]
