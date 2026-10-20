"""System tray app that runs the background runner and shows notifications."""

from __future__ import annotations

import logging
import sys
import threading

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from saveix.core import autostart
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
        from saveix.core.retention import retention_hook

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
        self.window = None
        self.open_action = QAction("Open SaveIX")
        self.open_action.triggered.connect(self.open_window)
        self.menu.addAction(self.open_action)
        self.menu.addSeparator()
        self.status = QAction("Watching for game sessions")
        self.status.setEnabled(False)
        self.pause_action = QAction("Pause backups")
        self.pause_action.triggered.connect(self.toggle_pause)
        self.log_action = QAction("Open log file")
        self.log_action.triggered.connect(self.open_log)
        self.autostart_action = QAction("Start with Windows")
        self.autostart_action.setCheckable(True)
        try:
            self.autostart_action.setChecked(autostart.is_enabled(self.run_key()))
        except autostart.AutostartUnavailableError:
            self.autostart_action.setEnabled(False)
        # Connected after setting the initial state, so opening the menu changes nothing.
        self.autostart_action.toggled.connect(self.set_autostart)
        quit_action = QAction("Quit")
        quit_action.triggered.connect(self.quit)
        for action in (self.status, self.pause_action):
            self.menu.addAction(action)
        self.menu.addSeparator()
        self.menu.addAction(self.autostart_action)
        self.menu.addAction(self.log_action)
        self.menu.addSeparator()
        self.menu.addAction(quit_action)
        self._actions = [quit_action]
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_activated)

        self.runner = RunnerThread(self.config)
        self.runner.notice.connect(self.on_notice)

    def start(self) -> None:
        self.tray.show()
        self.runner.start()

    def open_window(self) -> None:
        from saveix.ui.main_window import LibraryWindow

        if self.window is None:
            self.window = LibraryWindow(self.config)
        self.window.refresh()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def open_log(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from saveix.core.logs import log_file

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_file(self.config))))

    def run_key(self) -> autostart.RunKey | None:
        """The registry key used for autostart; tests replace it."""
        return None

    def set_autostart(self, enabled: bool) -> None:
        try:
            if enabled:
                autostart.enable(self.run_key())
            else:
                autostart.disable(self.run_key())
        except (autostart.AutostartUnavailableError, OSError) as exc:
            log.warning("could not change autostart: %s", exc)

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

    def on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_window()

    def quit(self) -> None:
        self.runner.stop()
        if self.window is not None:
            self.window.catalog.close()
        self.tray.hide()
        self.app.quit()


def main() -> int:
    from saveix import __version__
    from saveix.core.logs import setup_logging

    setup_logging(Config())
    log.info("saveix %s tray started", __version__)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("SaveIX")
    app.setWindowIcon(app_icon())
    tray = TrayApp(app)
    tray.start()
    return app.exec()
