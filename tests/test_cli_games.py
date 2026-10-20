import pytest
from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.sources import breadth_problem

runner = CliRunner()


@pytest.fixture(autouse=True)
def _home(fake_home):
    return fake_home


def run(*args):
    return runner.invoke(app, list(args))


def test_add_list_show_remove_game():
    assert run("game", "add", "Celeste").exit_code == 0
    assert "Celeste  (0 sources)" in run("game", "list").output
    assert run("game", "add", "celeste").exit_code == 1
    assert run("game", "remove", "Celeste", "--yes").exit_code == 0
    assert "No games yet" in run("game", "list").output


def test_add_folder_source_is_stored_as_template(fake_home):
    saves = fake_home / "AppData" / "LocalLow" / "Team Cherry" / "Hollow Knight"
    saves.mkdir(parents=True)
    run("game", "add", "Hollow Knight")

    result = run("source", "add", "Hollow Knight", str(saves), "--exclude", "*.log")
    assert result.exit_code == 0, result.output

    shown = run("game", "show", "Hollow Knight").output
    assert "folder   save   <locallow>/Team Cherry/Hollow Knight" in shown
    assert "exclude=*.log" in shown


def test_add_file_and_glob_sources(fake_home):
    docs = fake_home / "Documents" / "G"
    docs.mkdir(parents=True)
    (docs / "settings.ini").write_text("x")
    run("game", "add", "G")

    assert run("source", "add", "G", str(docs / "settings.ini"), "--role", "config").exit_code == 0
    assert run("source", "add", "G", "<documents>/G/*.sav").exit_code == 0
    shown = run("game", "show", "G").output
    assert "file     config <documents>/G/settings.ini" in shown
    assert "glob     save   <documents>/G/*.sav" in shown


def test_missing_path_needs_kind(fake_home):
    run("game", "add", "G")
    missing = str(fake_home / "AppData" / "Roaming" / "G")
    assert run("source", "add", "G", missing).exit_code == 1
    assert run("source", "add", "G", missing, "--kind", "folder").exit_code == 0


def test_too_broad_path_is_refused(fake_home):
    run("game", "add", "G")
    assert run("source", "add", "G", str(fake_home / "AppData" / "Roaming")).exit_code == 1
    result = run("source", "add", "G", str(fake_home / "AppData" / "Roaming"), "--force")
    assert result.exit_code == 0


def test_remove_source(fake_home):
    run("game", "add", "G")
    run("source", "add", "G", "<appdata>/G", "--kind", "folder")
    assert run("source", "remove", "G", "1").exit_code == 0
    assert run("source", "remove", "G", "1").exit_code == 1


def test_source_for_unknown_game_fails():
    assert run("source", "add", "Nope", "<appdata>/x", "--kind", "folder").exit_code == 1


@pytest.mark.parametrize(
    "template,broad",
    [("<appdata>", True), ("C:/", True), ("<home>/*", True), ("<appdata>/Game", False)],
)
def test_breadth_problem(template, broad):
    assert (breadth_problem(template) is not None) is broad
