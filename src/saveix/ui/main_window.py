"""The main window: the game library and each game's save locations."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from saveix.core.backup import BackupEngine, NothingToBackUpError
from saveix.core.catalog import Catalog, CatalogError
from saveix.core.config import Config
from saveix.core.context import context_for
from saveix.core.identify import identify
from saveix.core.models import Game, SourceKind
from saveix.core.models import Trigger as SnapshotTrigger
from saveix.core.sources import SourceError, make_source
from saveix.core.store import ObjectStore
from saveix.ui.dialogs import DetectDialog, ProviderSearchDialog


def _button(text: str, handler) -> QPushButton:
    button = QPushButton(text)
    button.clicked.connect(handler)
    return button


class LibraryWindow(QMainWindow):
    def __init__(self, config: Config | None = None) -> None:
        super().__init__()
        self.config = config or Config()
        self.catalog = Catalog(self.config.catalog_path)
        self.store = ObjectStore(self.config.backup_root)
        self.setWindowTitle("SaveIX")
        self.resize(1000, 640)

        self.games = QListWidget()
        self.games.currentItemChanged.connect(lambda *_: self.show_game())
        left = QVBoxLayout()
        left.addWidget(QLabel("Games"))
        left.addWidget(self.games)
        left.addWidget(_button("Add game…", self.ask_add_game))
        left.addWidget(_button("Remove game", self.remove_game))
        left_panel = QWidget()
        left_panel.setLayout(left)

        self.title = QLabel("Add a game to start backing up its saves.")
        self.title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.sources = QTableWidget(0, 4)
        self.sources.setHorizontalHeaderLabels(["Kind", "Role", "Location", "Added by"])
        header = self.sources.horizontalHeader()
        for column in (0, 1, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.sources.verticalHeader().setVisible(False)
        self.sources.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sources.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        add_row = QHBoxLayout()
        for text, handler in (
            ("Find in database…", self.open_search),
            ("Detect while playing…", self.open_detect),
            ("Add folder…", self.browse_folder),
            ("Add file…", self.browse_file),
            ("Add registry key…", self.ask_registry_key),
        ):
            add_row.addWidget(_button(text, handler))
        game_row = QHBoxLayout()
        for text, handler in (
            ("Remove location", self.remove_source),
            ("Set install folder…", self.browse_install),
            ("Back up now", self.backup_now),
        ):
            game_row.addWidget(_button(text, handler))
        game_row.addStretch()

        library_tab = QWidget()
        right = QVBoxLayout(library_tab)
        right.addWidget(self.info)
        right.addWidget(QLabel("Save locations"))
        right.addWidget(self.sources)
        right.addLayout(add_row)
        right.addLayout(game_row)

        self.tabs = QTabWidget()
        self.tabs.addTab(library_tab, "Save locations")
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(self.title)
        right_layout.addWidget(self.tabs)

        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([260, 740])
        self.setCentralWidget(splitter)
        self.refresh()

    # helpers

    def error(self, message: str) -> None:
        QMessageBox.warning(self, "SaveIX", message)

    def message(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

    def current_game(self) -> Game | None:
        item = self.games.currentItem()
        if item is None:
            return None
        try:
            return self.catalog.get_game(item.data(Qt.ItemDataRole.UserRole))
        except CatalogError:
            return None

    def refresh(self, select: str | None = None) -> None:
        current = select or (self.current_game().name if self.current_game() else None)
        self.games.blockSignals(True)
        self.games.clear()
        for game in self.catalog.list_games():
            item = QListWidgetItem(game.name)
            item.setData(Qt.ItemDataRole.UserRole, game.name)
            self.games.addItem(item)
            if game.name == current:
                self.games.setCurrentItem(item)
        if self.games.currentItem() is None and self.games.count():
            self.games.setCurrentRow(0)
        self.games.blockSignals(False)
        self.show_game()

    def show_game(self) -> None:
        game = self.current_game()
        self.sources.setRowCount(0)
        if game is None:
            self.title.setText("Add a game to start backing up its saves.")
            self.info.setText("")
            return
        self.title.setText(game.name)
        details = []
        if game.install_dir:
            details.append(f"Installed in {game.install_dir}")
        if game.steam_app_id:
            details.append(f"Steam app ID {game.steam_app_id}")
        if game.executables:
            details.append(f"Runs as {', '.join(game.executables)}")
        if game.cloud_sync:
            details.append("Also synced by a cloud service")
        self.info.setText(" · ".join(details) or "No install folder or executable set yet.")
        for source in game.sources:
            row = self.sources.rowCount()
            self.sources.insertRow(row)
            values = (source.kind.value, source.role.value, source.path, source.origin)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, source.id)
                self.sources.setItem(row, column, item)

    # games

    def ask_add_game(self) -> None:
        name, ok = QInputDialog.getText(self, "Add game", "Game name:")
        if ok and name.strip():
            self.add_game(name)

    def add_game(self, name: str) -> Game | None:
        try:
            game = self.catalog.add_game(name)
        except CatalogError as exc:
            self.error(str(exc))
            return None
        self.refresh(select=game.name)
        return game

    def remove_game(self) -> None:
        game = self.current_game()
        if game is None:
            return
        answer = QMessageBox.question(
            self, "Remove game", f"Remove {game.name}? Its snapshots are removed too."
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.catalog.remove_game(game.name)
            self.refresh()

    # sources

    def add_source_path(self, path: str, kind: SourceKind | None = None) -> bool:
        game = self.current_game()
        if game is None:
            return False
        try:
            source = make_source(path, context_for(game), kind)
            self.catalog.add_source(game, source)
        except (SourceError, CatalogError) as exc:
            self.error(str(exc))
            return False
        self.refresh()
        self.message(f"Added {source.path}")
        return True

    def browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a save folder")
        if folder:
            self.add_source_path(folder, SourceKind.FOLDER)

    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a save file")
        if path:
            self.add_source_path(path, SourceKind.FILE)

    def ask_registry_key(self) -> None:
        key, ok = QInputDialog.getText(
            self, "Add registry key", "Key under HKEY_CURRENT_USER, e.g. Software\\Studio\\Game:"
        )
        if ok and key.strip():
            key = key.strip()
            if not key.upper().startswith(("HKEY_", "HKCU")):
                key = "HKEY_CURRENT_USER\\" + key
            self.add_source_path(key, SourceKind.REGISTRY)

    def remove_source(self) -> None:
        game = self.current_game()
        row = self.sources.currentRow()
        if game is None or row < 0:
            return
        source_id = self.sources.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.catalog.remove_source(game, source_id)
        self.refresh()

    def browse_install(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose the game's install folder")
        if folder:
            self.set_install_folder(folder)

    def set_install_folder(self, folder: str) -> None:
        game = self.current_game()
        if game is None:
            return
        self.catalog.set_install_dir(game, str(Path(folder)))
        found = identify(Path(folder))
        if found.found and not (game.steam_app_id or game.gog_id):
            self.catalog.set_store_ids(game, found.steam_app_id, found.gog_id)
        self.refresh()

    def open_search(self) -> None:
        game = self.current_game()
        if game is not None:
            dialog = ProviderSearchDialog(self.config, self.catalog, game, parent=self)
            dialog.search()
            dialog.exec()
            self.refresh()

    def open_detect(self) -> None:
        game = self.current_game()
        if game is not None:
            DetectDialog(self.config, self.catalog, game, parent=self).exec()
            self.refresh()

    def backup_now(self) -> None:
        game = self.current_game()
        if game is None:
            return
        engine = BackupEngine(self.catalog, self.store)
        try:
            result = engine.backup(game, context_for(game), SnapshotTrigger.MANUAL)
        except NothingToBackUpError as exc:
            self.error(str(exc))
            return
        if result.unchanged:
            self.message("No changes since the last snapshot.")
        else:
            self.message(f"Saved snapshot #{result.snapshot.id}.")
        self.refresh()


def main() -> int:
    import sys

    from PySide6.QtWidgets import QApplication

    from saveix.ui.tray import app_icon

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SaveIX")
    app.setWindowIcon(app_icon())
    window = LibraryWindow()
    window.show()
    return app.exec()
