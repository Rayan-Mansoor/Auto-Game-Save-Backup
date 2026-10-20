import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from saveix.core.daemon import Notice  # noqa: E402
from saveix.ui.tray import TrayApp  # noqa: E402


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_tray_runs_watches_and_quits(qapp, fake_home):
    tray = TrayApp(qapp)
    tray.runner.interval = 0.05
    tray.start()
    assert tray.runner.isRunning()

    tray.toggle_pause()
    assert tray.runner.paused.is_set() and tray.status.text() == "Paused"
    tray.toggle_pause()
    assert not tray.runner.paused.is_set()

    tray.on_notice(Notice("Hollow Knight", "session ended; 2 snapshots saved", important=True))
    assert tray.status.text().startswith("Hollow Knight: session ended")

    tray.runner.stop()
    assert tray.runner.isFinished()
