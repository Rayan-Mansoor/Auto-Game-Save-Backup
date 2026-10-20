import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from saveix.core.config import Config  # noqa: E402
from saveix.core.models import SourceKind  # noqa: E402
from saveix.ui.main_window import LibraryWindow  # noqa: E402


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def save(path, text, second):
    path.write_text(text)
    os.utime(path, ns=(second * 10**9, second * 10**9))


@pytest.fixture
def window(qapp, fake_home, monkeypatch):
    w = LibraryWindow(Config())
    w.errors = []
    monkeypatch.setattr(w, "error", w.errors.append)
    w.timeline.on_error = w.errors.append
    w.timeline.confirm = lambda title, text: True
    saves = fake_home / "AppData/Roaming/G"
    saves.mkdir(parents=True)
    w.saves = saves
    w.add_game("G")
    w.add_source_path(str(saves), SourceKind.FOLDER)
    for second, text in enumerate(["stage 1", "stage 2", "stage 3"], start=1):
        save(saves / "slot.sav", text, second)
        w.backup_now()
    yield w
    w.catalog.close()


def test_timeline_lists_snapshots_newest_first(window):
    table = window.timeline.table
    assert table.rowCount() == 3
    assert [table.item(r, 1).text() for r in range(3)] == ["#3", "#2", "#1"]
    assert table.item(0, 0).text() == "✓"
    assert "Changes since #2" in window.timeline.details.toPlainText()


def test_label_note_pin(window, monkeypatch):
    tab = window.timeline
    tab.table.selectRow(2)
    snap = tab.selected()
    window.catalog.set_label(snap.id, "Act 1")
    window.catalog.set_note(snap.id, "before the boss")
    tab.toggle_pin()
    tab.refresh()
    assert tab.selected().id == snap.id
    assert tab.table.item(2, 3).text() == "Act 1  📌"
    assert "Note: before the boss" in tab.details.toPlainText()
    assert tab.buttons["pin"].text() == "Unpin"


def test_restore_any_snapshot(window, monkeypatch):
    monkeypatch.setattr("saveix.ui.timeline_view.running_games", lambda games: [])
    tab = window.timeline
    tab.table.selectRow(2)
    assert tab.restore_selected()
    assert (window.saves / "slot.sav").read_text() == "stage 1"
    # Restoring again changes nothing; the newer snapshots are all still there.
    tab.table.selectRow(2)
    assert not tab.restore_selected()
    assert tab.table.rowCount() == 3


def test_restore_refused_while_running(window, monkeypatch):
    monkeypatch.setattr("saveix.ui.timeline_view.running_games", lambda games: games)
    window.timeline.table.selectRow(1)
    assert not window.timeline.restore_selected()
    assert "is running" in window.errors[-1]
