"""The timeline tab: every snapshot of a game, and restoring any of them."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from saveix.core.backup import BackupEngine
from saveix.core.catalog import Catalog
from saveix.core.context import context_for
from saveix.core.diff import Change, diff_files
from saveix.core.models import Game, Snapshot
from saveix.core.restore import Action, Restorer, cloud_warning
from saveix.core.sessions import running_games
from saveix.core.store import CorruptObjectError, ObjectStore
from saveix.core.text import human_size
from saveix.core.timeline import timeline

HEALTH_TEXT = {"ok": "✓", "suspicious": "⚠", None: ""}
SYMBOLS = {Change.ADDED: "+", Change.REMOVED: "−", Change.MODIFIED: "~"}


class TimelineTab(QWidget):
    def __init__(
        self,
        catalog: Catalog,
        store: ObjectStore,
        current_game: Callable[[], Game | None],
        on_error: Callable[[str], None],
        on_message: Callable[[str], None],
    ) -> None:
        super().__init__()
        self.catalog, self.store = catalog, store
        self.current_game = current_game
        self.on_error, self.on_message = on_error, on_message
        self.confirm: Callable[[str, str], bool] = self._ask

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "#", "When", "Label", "Files", "Size"])
        header = self.table.horizontalHeader()
        for column in (0, 1, 2, 4, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.show_details)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(170)

        buttons = QHBoxLayout()
        self.buttons = {}
        for key, text, handler in (
            ("label", "Rename…", self.ask_label),
            ("note", "Note…", self.ask_note),
            ("pin", "Pin", self.toggle_pin),
            ("restore", "Restore this snapshot…", self.restore_selected),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons.addWidget(button)
            self.buttons[key] = button
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Every snapshot, newest first. Pick any point to go back to."))
        layout.addWidget(self.table)
        layout.addWidget(self.details)
        layout.addLayout(buttons)
        self.refresh()

    def _ask(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, title, text)
        return answer == QMessageBox.StandardButton.Yes

    def selected(self) -> Snapshot | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.catalog.get_snapshot(self.table.item(row, 1).data(Qt.ItemDataRole.UserRole))

    def refresh(self) -> None:
        # Stay on the newest snapshot when new ones arrive; otherwise keep the selection.
        selected = self.selected() if self.table.currentRow() > 0 else None
        game = self.current_game()
        self.table.setRowCount(0)
        for entry in timeline(self.catalog, game) if game else []:
            snap = entry.snapshot
            row = self.table.rowCount()
            self.table.insertRow(row)
            label = entry.label + ("  📌" if snap.pinned else "")
            values = (
                HEALTH_TEXT.get(snap.health, ""),
                f"#{snap.id}",
                entry.local_time.strftime("%Y-%m-%d %H:%M"),
                label,
                str(snap.file_count),
                human_size(snap.total_size),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, snap.id)
                if column == 3 and entry.custom_label:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, column, item)
            if selected and snap.id == selected.id:
                self.table.selectRow(row)
        if self.table.currentRow() < 0 and self.table.rowCount():
            self.table.selectRow(0)
        self.show_details()

    def show_details(self) -> None:
        snap = self.selected()
        for button in self.buttons.values():
            button.setEnabled(snap is not None)
        if snap is None:
            self.details.setPlainText("")
            return
        self.buttons["pin"].setText("Unpin" if snap.pinned else "Pin")
        lines = []
        if snap.note:
            lines.append(f"Note: {snap.note}")
        lines += [f"⚠ {problem}" for problem in snap.health_notes]
        previous = self.catalog.previous_snapshot(snap)
        if previous:
            changes = diff_files(
                self.catalog.snapshot_files(previous.id), self.catalog.snapshot_files(snap.id)
            )
            lines.append(f"Changes since #{previous.id}:" if changes else "Same as the previous.")
            lines += [f"  {SYMBOLS[c.change]} {c.template}" for c in changes]
        else:
            lines.append("First snapshot of this game.")
        self.details.setPlainText("\n".join(lines))

    def ask_label(self) -> None:
        snap = self.selected()
        if snap is None:
            return
        text, ok = QInputDialog.getText(
            self, "Rename snapshot", "Label (empty for automatic):", text=snap.label or ""
        )
        if ok:
            self.catalog.set_label(snap.id, text)
            self.refresh()

    def ask_note(self) -> None:
        snap = self.selected()
        if snap is None:
            return
        text, ok = QInputDialog.getMultiLineText(self, "Snapshot note", "Note:", snap.note or "")
        if ok:
            self.catalog.set_note(snap.id, text)
            self.refresh()

    def toggle_pin(self) -> None:
        snap = self.selected()
        if snap is not None:
            self.catalog.set_pinned(snap.id, not snap.pinned)
            self.refresh()

    def restore_selected(self) -> bool:
        game, snap = self.current_game(), self.selected()
        if game is None or snap is None:
            return False
        if running_games([game]):
            self.on_error(f"{game.name} is running; close it before restoring its saves.")
            return False
        context = context_for(game)
        restorer = Restorer(self.catalog, self.store, BackupEngine(self.catalog, self.store))
        plan = restorer.plan(game, snap, context)
        if not plan.has_changes:
            self.on_message(f"{game.name}'s saves already match snapshot #{snap.id}.")
            return False
        lines = [f"write  {f.template}" for f in plan.of(Action.WRITE)]
        lines += [f"delete {f.template}" for f in plan.of(Action.DELETE)]
        text = f"Restore {game.name} to snapshot #{snap.id}?\n\n" + "\n".join(lines[:15])
        if len(lines) > 15:
            text += f"\n… and {len(lines) - 15} more"
        text += "\n\nYour current saves are kept as a new snapshot first."
        warning = cloud_warning(game)
        if warning:
            text += f"\n\n{warning}"
        if not self.confirm("Restore snapshot", text):
            return False
        try:
            result = restorer.execute(plan, context)
        except CorruptObjectError as exc:
            self.on_error(str(exc))
            return False
        self.on_message(f"Restored {result.written} files from snapshot #{snap.id}.")
        self.refresh()
        return True
