# views/deck_picker.py
"""Modal dialog for choosing an Anki deck and saving a note."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton,
)

from views.theme import Theme
from utils.app_logger import get_logger

logger = get_logger(__name__)


class DeckPickerDialog(QDialog):
    """Show a deck picker, create decks, and save an Anki note."""

    saved = Signal()

    # Background-thread controller callbacks funnel through these signals.
    _decks_loaded = Signal(bool, list)
    _deck_created = Signal(dict)
    _save_finished = Signal(dict)

    def __init__(self, controller, word, src_lang: str, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._word = word
        self._src_lang = src_lang

        self.setWindowTitle("Save to Anki")
        self.setStyleSheet(f"QDialog {{ background: {Theme.CARD_BG}; }}")
        self.setFixedWidth(340)

        self._decks_loaded.connect(self._on_decks_loaded)
        self._deck_created.connect(self._apply_create_result)
        self._save_finished.connect(self._apply_save_result)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Choose deck:"))

        self._combo = QComboBox()
        self._combo.setEditable(False)
        self._combo.setEnabled(False)
        self._combo.addItem("Loading…")
        layout.addWidget(self._combo)

        new_deck_row = QHBoxLayout()
        self._new_entry = QLineEdit()
        self._new_entry.setPlaceholderText("New deck name")
        self._new_entry.returnPressed.connect(self._do_create_deck)
        self._new_entry.hide()
        new_deck_row.addWidget(self._new_entry)

        self._new_btn = QPushButton("+ New Deck")
        self._new_btn.setFlat(True)
        self._new_btn.clicked.connect(self._show_new_entry)
        new_deck_row.addWidget(self._new_btn)

        self._create_btn = QPushButton("Create")
        self._create_btn.setProperty("variant", "success")
        self._create_btn.clicked.connect(self._do_create_deck)
        self._create_btn.hide()
        new_deck_row.addWidget(self._create_btn)
        layout.addLayout(new_deck_row)

        self._status = QLabel("Starting Anki…")
        self._status.setProperty("role", "muted")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.setProperty("variant", "success")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._controller.ensure_anki_ready(on_ready=self._decks_loaded.emit)

    # ── new-deck helpers ──────────────────────────────────────────────
    def _show_new_entry(self):
        self._new_btn.hide()
        self._new_entry.show()
        self._create_btn.show()
        self._new_entry.setFocus()

    def _do_create_deck(self):
        name = self._new_entry.text().strip()
        if not name:
            return
        self._create_btn.setEnabled(False)
        self._create_btn.setText("…")
        self._controller.create_anki_deck(name, on_ready=self._deck_created.emit)
        self._pending_deck_name = name

    def _apply_create_result(self, result: dict):
        try:
            if result["success"]:
                name = self._pending_deck_name
                self._combo.addItem(name)
                self._combo.setCurrentText(name)
                self._new_entry.clear()
                self._new_entry.hide()
                self._create_btn.hide()
                self._new_btn.show()
                self._status.setText(f'Deck "{name}" created.')
                self._status.setStyleSheet(f"color: {Theme.GREEN};")
            else:
                self._status.setText(result["error"])
                self._status.setStyleSheet(f"color: {Theme.RED};")
        except Exception:
            logger.exception("Failed to apply deck-create result: %r", result)
            self._status.setText("Unexpected error creating deck.")
            self._status.setStyleSheet(f"color: {Theme.RED};")
        self._create_btn.setEnabled(True)
        self._create_btn.setText("Create")

    # ── connect to Anki ───────────────────────────────────────────────
    def _on_decks_loaded(self, anki_ok: bool, decks: list):
        self._combo.clear()
        self._combo.setEnabled(True)
        if decks:
            self._combo.addItems(decks)
            self._status.setText("")
        elif anki_ok:
            self._combo.addItem("Default")
            self._status.setText("No decks found — type a name to create one.")
            self._status.setStyleSheet(f"color: {Theme.MUTED_FG};")
        else:
            self._combo.addItem("Default")
            self._status.setText("Could not start Anki. Is it installed with AnkiConnect?")
            self._status.setStyleSheet(f"color: {Theme.RED};")

    # ── save ──────────────────────────────────────────────────────────
    def _on_save(self):
        deck_name = self._combo.currentText().strip()
        if not deck_name:
            self._status.setText("Enter a deck name.")
            self._status.setStyleSheet(f"color: {Theme.RED};")
            return

        self._save_btn.setEnabled(False)
        self._save_btn.setText("Saving…")
        self._controller.save_to_anki(
            self._word, deck_name, self._src_lang, on_ready=self._save_finished.emit,
        )

    def _apply_save_result(self, result: dict):
        try:
            if result["success"]:
                self._status.setText("Saved!")
                self._status.setStyleSheet(f"color: {Theme.GREEN};")
                self.saved.emit()
                self.accept()
            else:
                self._status.setText(result["error"])
                self._status.setStyleSheet(f"color: {Theme.RED};")
                self._save_btn.setEnabled(True)
                self._save_btn.setText("Save")
        except Exception:
            logger.exception("Failed to apply Anki save result: %r", result)
            self._status.setText("Unexpected error saving note.")
            self._status.setStyleSheet(f"color: {Theme.RED};")
            self._save_btn.setEnabled(True)
            self._save_btn.setText("Save")
