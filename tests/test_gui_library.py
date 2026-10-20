import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from saveix.core.config import Config  # noqa: E402
from saveix.core.models import SourceKind  # noqa: E402
from saveix.ui.dialogs import DetectDialog, ProviderSearchDialog, checked_items  # noqa: E402
from saveix.ui.main_window import LibraryWindow  # noqa: E402
from tests import fake_provider  # noqa: E402


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, fake_home, monkeypatch):
    errors = []
    w = LibraryWindow(Config())
    monkeypatch.setattr(w, "error", errors.append)
    w.errors = errors
    yield w
    w.catalog.close()


def test_add_game_and_locations(window, fake_home, tmp_path):
    saves = fake_home / "AppData/LocalLow/Team Cherry/Hollow Knight"
    saves.mkdir(parents=True)
    (saves / "user1.dat").write_text("progress")

    window.add_game("Hollow Knight")
    assert window.games.count() == 1 and window.title.text() == "Hollow Knight"
    assert window.add_source_path(str(saves), SourceKind.FOLDER)
    assert window.sources.item(0, 2).text() == "<locallow>/Team Cherry/Hollow Knight"

    assert not window.add_source_path(str(fake_home / "AppData/Roaming"), SourceKind.FOLDER)
    assert "whole system folder" in window.errors[-1]
    assert window.add_game("hollow knight") is None

    install = tmp_path / "HK"
    install.mkdir()
    (install / "steam_appid.txt").write_text("367520")
    window.set_install_folder(str(install))
    assert "Steam app ID 367520" in window.info.text()

    window.backup_now()
    assert window.catalog.latest_snapshot(window.current_game()).file_count == 1

    window.sources.selectRow(0)
    window.remove_source()
    assert window.sources.rowCount() == 0


def test_provider_search_dialog(window, fake_home):
    saves = fake_home / "AppData/LocalLow/Team Cherry/Hollow Knight"
    saves.mkdir(parents=True)
    (saves / "user1.dat").write_text("progress")
    game = window.add_game("Hollow Knight")
    provider = fake_provider.factory(None)
    dialog = ProviderSearchDialog(window.config, window.catalog, game, providers=[provider])

    assert [m.name for m in dialog.search()] == ["Hollow Knight"]
    dialog.matches.setCurrentRow(0)
    assert [i.text().split("   ")[0] for i in checked_items(dialog.candidates)] == [
        "save: <locallow>/Team Cherry/Hollow Knight/*.dat"
    ]
    dialog.add_selected()
    game = window.catalog.get_game("Hollow Knight")
    assert [s.path for s in game.sources] == ["<locallow>/Team Cherry/Hollow Knight/*.dat"]
    assert game.executables == ["hollow_knight.exe"] and game.cloud_sync


def test_provider_dialog_without_providers(window):
    game = window.add_game("G")
    dialog = ProviderSearchDialog(window.config, window.catalog, game, providers=[])
    assert "No save databases are enabled" in dialog.status.text()


def test_detect_dialog(window, fake_home):
    saves = fake_home / "AppData/LocalLow/Team Cherry/Hollow Knight"
    saves.mkdir(parents=True)
    game = window.add_game("Hollow Knight")
    dialog = DetectDialog(window.config, window.catalog, game)
    time.sleep(0.5)
    (saves / "user1.dat").write_text("progress")
    deadline = time.time() + 10
    while not dialog.recorder.paths() and time.time() < deadline:
        threading.Event().wait(0.1)
    suggestions = dialog.finish()
    assert suggestions[0].template == "<locallow>/Team Cherry/Hollow Knight"
    assert dialog.results.item(0).checkState() == Qt.CheckState.Checked
    dialog.add_selected()
    assert window.catalog.get_game("Hollow Knight").sources[0].origin == "detected"
