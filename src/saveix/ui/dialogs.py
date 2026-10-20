"""Dialogs for adding save locations: assisted detection and provider search."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from saveix.core.catalog import Catalog, CatalogError
from saveix.core.config import Config
from saveix.core.context import context_for
from saveix.core.detect import ChangeRecorder, Suggestion, detection_roots, suggest
from saveix.core.emulators import load_emulators
from saveix.core.models import Game, Source, SourceKind
from saveix.core.providers import GameMatch, Provider, load_providers
from saveix.core.suggestions import CheckedCandidate, apply_details, check_candidates
from saveix.core.watcher import WatchdogWatcher


def checked_items(widget: QListWidget) -> list[QListWidgetItem]:
    items = (widget.item(i) for i in range(widget.count()))
    return [item for item in items if item.checkState() == Qt.CheckState.Checked]


def add_checkable(widget: QListWidget, text: str, data: object, checked: bool) -> None:
    item = QListWidgetItem(text)
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    item.setData(Qt.ItemDataRole.UserRole, data)
    widget.addItem(item)


class DetectDialog(QDialog):
    """Watch the save folders while the user plays, then offer what changed."""

    def __init__(self, config: Config, catalog: Catalog, game: Game, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Detect saves for {game.name}")
        self.catalog, self.game = catalog, game
        self.context = context_for(game)
        self.recorder = ChangeRecorder(ignore=[config.dirs.data_dir, config.backup_root])
        self.watcher = WatchdogWatcher()

        self.status = QLabel(
            f"Watching. Start {game.name}, play until it saves, quit the game, then click Done."
        )
        self.status.setWordWrap(True)
        self.results = QListWidget()
        self.done_button = QPushButton("Done")
        self.done_button.clicked.connect(self.finish)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add selected")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.add_selected)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        for widget in (self.status, self.done_button, self.results, self.buttons):
            layout.addWidget(widget)
        self.resize(640, 420)
        self.watcher.start(detection_roots(self.context), self.recorder)

    def finish(self) -> list[Suggestion]:
        self.watcher.stop()
        self.done_button.setEnabled(False)
        suggestions = suggest(self.recorder.paths(), self.context, self.game.name)[:8]
        for index, item in enumerate(suggestions):
            add_checkable(
                self.results,
                f"{item.template}   ({len(item.files)} files changed)",
                item,
                index == 0,
            )
        if suggestions:
            self.status.setText("These folders changed while you played. Tick the save folders.")
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        else:
            self.status.setText("No likely save files were written. Make sure the game saved.")
        return suggestions

    def add_selected(self) -> None:
        for item in checked_items(self.results):
            suggestion: Suggestion = item.data(Qt.ItemDataRole.UserRole)
            try:
                self.catalog.add_source(
                    self.game, Source(SourceKind.FOLDER, suggestion.template, origin="detected")
                )
            except CatalogError:
                pass
        self.accept()

    def reject(self) -> None:
        self.watcher.stop()
        super().reject()


class ProviderSearchDialog(QDialog):
    """Search enabled providers and add the suggested locations that exist here."""

    def __init__(
        self,
        config: Config,
        catalog: Catalog,
        game: Game,
        providers: list[Provider] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Find save locations for {game.name}")
        self.config, self.catalog, self.game = config, catalog, game
        if providers is None:
            providers = load_providers(config.settings.providers, config.dirs.data_dir)
        self.providers = providers
        self.details = None

        self.query = QLineEdit(game.name)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        self.matches = QListWidget()
        self.matches.currentItemChanged.connect(lambda item, _: self.show_match(item))
        self.candidates = QListWidget()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add selected")
        self.buttons.accepted.connect(self.add_selected)
        self.buttons.rejected.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(self.query)
        row.addWidget(search_button)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(QLabel("Games"))
        layout.addWidget(self.matches)
        layout.addWidget(QLabel("Save locations (ticked ones exist on this PC)"))
        layout.addWidget(self.candidates)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)
        self.resize(720, 560)

        if not self.providers:
            self.status.setText(
                "No save databases are enabled. Enable one with "
                "`saveix providers enable ludusavi` and `saveix providers update`."
            )
            search_button.setEnabled(False)

    def search(self) -> list[GameMatch]:
        self.matches.clear()
        self.candidates.clear()
        found: list[GameMatch] = []
        for provider in self.providers:
            for match in provider.search(self.query.text(), limit=15):
                found.append(match)
                item = QListWidgetItem(f"{match.name}   [{provider.name}]")
                item.setData(Qt.ItemDataRole.UserRole, (provider, match))
                self.matches.addItem(item)
        self.status.setText("" if found else "No matches.")
        return found

    def show_match(self, item: QListWidgetItem | None) -> list[CheckedCandidate]:
        self.candidates.clear()
        if item is None:
            return []
        provider, match = item.data(Qt.ItemDataRole.UserRole)
        self.details = provider.details(match)
        emulators = load_emulators(self.config.dirs.config_dir / "emulators.json")
        checked = check_candidates(self.details, self.game, context_for(self.game), emulators)
        for candidate in checked:
            where = f"{candidate.files} files" if candidate.exists else "not on this PC"
            note = f", {candidate.note}" if candidate.note else ""
            text = f"{candidate.source.role.value}: {candidate.source.path}   ({where}{note})"
            add_checkable(self.candidates, text, candidate, candidate.exists)
        if not checked:
            self.status.setText("This database lists no usable Windows save locations.")
        return checked

    def add_selected(self) -> None:
        for item in checked_items(self.candidates):
            candidate: CheckedCandidate = item.data(Qt.ItemDataRole.UserRole)
            try:
                self.catalog.add_source(self.game, candidate.source)
            except CatalogError:
                pass
        if self.details is not None:
            apply_details(self.catalog, self.game, self.details)
        self.accept()
