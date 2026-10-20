"""System tray app that runs the background runner and shows notifications."""

from __future__ import annotations

import logging
import sys
import threading

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from saveix.core.backup import BackupEngine
from saveix.core.catalog import Catalog
from saveix.core.config import Config
from saveix.core.daemon import Notice, Runner
from saveix.core.store import ObjectStore

log = logging.getLogger("saveix")


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#2f6fdf"))
    painter.setPen(QColor("#2f6fdf"))
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Arial", 30, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    painter.end()
    return QIcon(pixmap)


class RunnerThread(QThread):
    """Runs the runner off the UI thread with its own catalog connection."""

    notice = Signal(object)

    def __init__(self, config: Config, interval: float = 5.0) -> None:
        super().__init__()
        self.config = config
        self.interval = interval
        self.stop_event = threading.Event()
        self.paused = threading.Event()

    def run(self) -> None:
        from saveix.cli.prune import retention_hook

        catalog = Catalog(self.config.catalog_path)
        try:
            settings = self.config.settings
            runner = Runner(
                catalog,
                BackupEngine(catalog, ObjectStore(self.config.backup_root)),
                notify=self.notice.emit,
                retention=retention_hook(self.config, catalog),
                quiet_period=settings.quiet_period_seconds,
                checkpoint_interval=settings.checkpoint_interval_minutes * 60,
            )
            while not self.stop_event.is_set():
                if not self.paused.is_set():
                    try:
                        runner.poll()
                    except Exception:
                        log.exception("polling failed")
                self.stop_event.wait(self.interval)
            runner.stop_watching()
        finally:
            catalog.close()

    def stop(self) -> None:
        self.stop_event.set()
        self.wait(15000)


class TrayApp(QObject):
    def __init__(self, app: QApplication, config: Config | None = None) -> None:
        super().__init__()
        self.app = app
        self.config = config or Config()
        self.icon = app_icon()
        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip("SaveIX: watching for game sessions")
        self.menu = QMenu()
        self.status = QAction("Watching for game sessions")
        self.status.setEnabled(False)
        self.pause_action = QAction("Pause backups")
        self.pause_action.triggered.connect(self.toggle_pause)
        quit_action = QAction("Quit")
        quit_action.triggered.connect(self.quit)
        for action in (self.status, self.pause_action):
            self.menu.addAction(action)
        self.menu.addSeparator()
        self.menu.addAction(quit_action)
        self._actions = [quit_action]
        self.tray.setContextMenu(self.menu)

        self.runner = RunnerThread(self.config)
        self.runner.notice.connect(self.on_notice)

    def start(self) -> None:
        self.tray.show()
        self.runner.start()

    def toggle_pause(self) -> None:
        if self.runner.paused.is_set():
            self.runner.paused.clear()
            self.pause_action.setText("Pause backups")
            self.status.setText("Watching for game sessions")
        else:
            self.runner.paused.set()
            self.pause_action.setText("Resume backups")
            self.status.setText("Paused")

    def on_notice(self, notice: Notice) -> None:
        self.status.setText(f"{notice.game}: {notice.message}"[:80])
        if notice.important and QSystemTrayIcon.supportsMessages():
            kind = (
                QSystemTrayIcon.MessageIcon.Warning
                if notice.warning
                else QSystemTrayIcon.MessageIcon.Information
            )
            self.tray.showMessage(notice.game, notice.message, kind, 8000)

    def quit(self) -> None:
        self.runner.stop()
        self.tray.hide()
        self.app.quit()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("SaveIX")
    app.setWindowIcon(app_icon())
    tray = TrayApp(app)
    tray.start()
    return app.exec()
