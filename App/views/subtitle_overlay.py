# views/subtitle_overlay.py
"""
Borderless, always-on-top subtitle bar with centered word-wrap.

Hover  → quick definition card.
Click  → pinned detail window with COMPLETE info (pronunciation, meanings, forms, examples).
"""

from PySide6.QtCore import Qt, Signal, QPoint, QTimer
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QDialog,
    QScrollArea, QPushButton, QApplication,
)

from services.definition_service import (
    LANG_NAMES, SKIP_TAGS,
    pick_pronunciations, pick_forms, is_inflection_definition,
)
from utils.app_logger import get_logger
from views.theme import Theme

logger = get_logger(__name__)
MAX_SENSES = 4
WORD_FONT = QFont("Segoe UI", 22, QFont.Weight.Bold)  # must match Theme.FONT_WORD, used for measuring line widths


class WordLabel(QLabel):
    """A single clickable/hoverable word in the subtitle bar."""

    hovered = Signal(object, object)   # (word, label)
    left = Signal()
    clicked = Signal(object)           # word

    def __init__(self, word_obj):
        super().__init__(word_obj.text)
        self.word_obj = word_obj
        self._style_template = (
            "color: {fg}; background: transparent; padding: 2px 6px; "
            "font-family: 'Segoe UI'; font-size: 22px; font-weight: bold;"
        )
        self.setStyleSheet(self._style_template.format(fg=Theme.FG))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):
        self.setStyleSheet(self._style_template.format(fg=Theme.HOVER_FG))
        self.hovered.emit(self.word_obj, self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self._style_template.format(fg=Theme.FG))
        self.left.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit(self.word_obj)
        super().mousePressEvent(event)


class HoverCard(QFrame):
    """Small popup shown under a word on hover — quick definition preview."""

    definition_ready = Signal(object)  # word, emitted from a background thread

    def __init__(self, controller, get_src_lang, get_tgt_lang):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                          | Qt.WindowType.WindowStaysOnTopHint)
        self._controller = controller
        self._get_src_lang = get_src_lang
        self._get_tgt_lang = get_tgt_lang
        self.setStyleSheet(
            f"QFrame {{ background: {Theme.CARD_BG}; border: 1px solid {Theme.BORDER}; "
            f"border-radius: 10px; }}"
        )
        self.definition_ready.connect(self._apply_definition)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._title = QLabel()
        self._title.setStyleSheet(f"color: {Theme.CARD_TITLE_FG}; {Theme.font_css(Theme.FONT_CARD_TITLE)}")
        layout.addWidget(self._title)

        self._source = QLabel()
        self._source.setStyleSheet(f"color: {Theme.CARD_GRAM_FG}; {Theme.font_css(Theme.FONT_CARD_META)}")
        layout.addWidget(self._source)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {Theme.BORDER};")
        layout.addWidget(divider)

        self._definition = QLabel()
        self._definition.setStyleSheet(f"color: {Theme.CARD_DEF_FG}; {Theme.font_css(Theme.FONT_CARD_BODY)}")
        self._definition.setWordWrap(True)
        self._definition.setMaximumWidth(320)
        layout.addWidget(self._definition)

        self._grammar = QLabel()
        self._grammar.setStyleSheet(f"color: {Theme.CARD_GRAM_FG}; {Theme.font_css(Theme.FONT_CARD_POS)}")
        layout.addWidget(self._grammar)

        self._error = QLabel()
        self._error.setStyleSheet(f"color: {Theme.CARD_ERR_FG}; {Theme.font_css(Theme.FONT_CARD_META)}")
        layout.addWidget(self._error)

        self._current_word = None

    def show_for(self, word_obj, anchor_global_pos: QPoint):
        self._current_word = word_obj
        self._title.setText(word_obj.text)
        src_name = LANG_NAMES.get(self._get_src_lang(), self._get_src_lang())
        self._source.setText(f"from {src_name}")
        self._definition.setText("Loading…")
        self._grammar.setText("")
        self._error.setText("")

        self.adjustSize()
        x, y = anchor_global_pos.x(), anchor_global_pos.y()
        screen_w = QApplication.primaryScreen().geometry().width()
        if x + self.width() > screen_w:
            x = screen_w - self.width() - 10
        self.move(x, y)
        self.show()

        self._controller.fetch_hover_definition(
            word_obj, self._get_src_lang(), self._get_tgt_lang(),
            on_ready=self.definition_ready.emit,
        )

    def _apply_definition(self, word):
        if word is not self._current_word or not self.isVisible():
            return
        try:
            result = word.simple_result or {}
            if result.get("error"):
                self._definition.setText("")
                self._grammar.setText("")
                self._error.setText(f"⚠️ {result['error']}")
                return
            self._definition.setText(word.definition or "No definition found.")
            self._grammar.setText(f"• {word.grammar}" if word.grammar else "")
            self._error.setText("")
            self.adjustSize()
        except Exception:
            logger.exception("Failed to render hover definition for word=%r", word.text)
            self._error.setText("⚠️ Could not display definition")


class DetailDialog(QDialog):
    """Pinned full-detail card — pronunciation, senses, forms, Anki export."""

    details_ready = Signal(object)  # word, emitted from a background thread

    def __init__(self, controller, word_obj, src_lang, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Word Details")
        self.setStyleSheet(f"QDialog {{ background: {Theme.CARD_BG}; }}")
        self.resize(520, 640)

        self._controller = controller
        self._word = word_obj
        self._src_lang = src_lang
        self.details_ready.connect(self._apply_details)

        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        outer.addWidget(scroll)

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 16, 20, 16)
        self._content_layout.setSpacing(4)
        scroll.setWidget(self._content)

        title = QLabel(word_obj.text)
        title.setStyleSheet(f"color: {Theme.CARD_TITLE_FG}; {Theme.font_css(Theme.FONT_CARD_TITLE)}")
        self._content_layout.addWidget(title)

        src_name = LANG_NAMES.get(src_lang, src_lang)
        source = QLabel(f"from {src_name}")
        source.setStyleSheet(
            f"color: {Theme.CARD_GRAM_FG}; margin-bottom: 8px; {Theme.font_css(Theme.FONT_CARD_META)}"
        )
        self._content_layout.addWidget(source)

        self._body = QVBoxLayout()
        self._body.setSpacing(4)
        self._content_layout.addLayout(self._body)
        self._loading_label = QLabel("Loading…")
        self._loading_label.setStyleSheet(f"color: {Theme.CARD_DEF_FG};")
        self._body.addWidget(self._loading_label)
        self._content_layout.addStretch(1)

        btn_row = QHBoxLayout()
        self._anki_btn = QPushButton("+ Anki")
        self._anki_btn.setProperty("variant", "success")
        self._anki_btn.setEnabled(False)
        self._anki_btn.clicked.connect(self._save_to_anki)
        btn_row.addWidget(self._anki_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("✕ Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

        self._controller.fetch_full_definition(
            word_obj, src_lang, "en",
            on_ready=self.details_ready.emit,
        )

    def _clear_body(self):
        while self._body.count():
            item = self._body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_section_header(self, text: str):
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"color: {Theme.CARD_SECTION_FG}; margin-top: 10px; {Theme.font_css(('Segoe UI', 10, 'bold'))}"
        )
        self._body.addWidget(lbl)

    def _add_body_label(self, text: str, color: str, font_spec=Theme.FONT_CARD_BODY, wrap=True):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; {Theme.font_css(font_spec)}")
        lbl.setWordWrap(wrap)
        self._body.addWidget(lbl)
        return lbl

    def _apply_details(self, word):
        try:
            self._render_details(word)
        except Exception:
            logger.exception("Failed to render word details for word=%r", word.text)
            self._clear_body()
            self._add_body_label("⚠️ Could not display details for this word", Theme.CARD_ERR_FG)

    def _render_details(self, word):
        self._clear_body()
        simple_result = word.simple_result or {}
        detail_result = word.detail_result or {}

        if simple_result.get("error") and detail_result.get("error"):
            self._add_body_label(f"⚠️ Error: {simple_result['error']}", Theme.CARD_ERR_FG)
            return

        d = word.details

        pos = d.get("partOfSpeech", word.grammar)
        if pos:
            self._add_body_label(f"• {pos}", Theme.CARD_GRAM_FG, Theme.FONT_CARD_POS)

        prons = pick_pronunciations(d.get("pronunciations", []), self._src_lang)
        if prons:
            self._add_section_header("Pronunciation")
            for p in prons:
                tags = p.get("tags", [])
                tag_str = f" ({', '.join(tags)})" if tags else ""
                self._add_body_label(f"  {p.get('text', '')}{tag_str}", Theme.CARD_PRON_FG, Theme.FONT_CARD_PRON)

        self._add_section_header("Meanings")
        simple_def = word.definition
        if simple_def and simple_def != "No definition found.":
            self._add_body_label(f"• {simple_def}", Theme.CARD_DEF_FG)

        senses = d.get("senses", [])
        if senses:
            filtered = [s for s in senses if not (set(s.get("tags", [])) & SKIP_TAGS)]
            real = [s for s in filtered if not is_inflection_definition(s.get("definition", ""))]
            infl = [s for s in filtered if is_inflection_definition(s.get("definition", ""))]
            chosen = (real or infl)[:MAX_SENSES]

            for i, s in enumerate(chosen, start=1):
                defi = s.get("definition", "")
                if defi == simple_def:
                    continue
                tags = s.get("tags", [])
                tag_str = f" [{', '.join(tags)}]" if tags else ""
                self._add_body_label(f"{i}. {defi}{tag_str}", Theme.CARD_DEF_FG)

                examples = s.get("examples", [])
                if examples:
                    self._add_body_label(f"    e.g. {examples[0]}", Theme.CARD_EXAMPLE_FG, Theme.FONT_CARD_EXAMPLE)

                synonyms = s.get("synonyms", [])
                if synonyms:
                    self._add_body_label(f"    ≈ {', '.join(synonyms[:6])}", Theme.CARD_SYN_FG, Theme.FONT_CARD_META)

                antonyms = s.get("antonyms", [])
                if antonyms:
                    self._add_body_label(f"    ≠ {', '.join(antonyms[:6])}", Theme.CARD_ANT_FG, Theme.FONT_CARD_META)

        forms = pick_forms(d.get("forms", []))
        if forms:
            self._add_section_header("Key Forms")
            for f in forms:
                tags = f.get("tags", [])
                tag_str = f" — {', '.join(tags)}" if tags else ""
                self._add_body_label(f"  • {f.get('word', '')}{tag_str}", Theme.CARD_DEF_FG)

        self._anki_btn.setEnabled(True)

    def _save_to_anki(self):
        if not self._word.is_definition_loaded:
            return
        from views.deck_picker import DeckPickerDialog
        dlg = DeckPickerDialog(self._controller, self._word, self._src_lang, parent=self)
        dlg.saved.connect(lambda: self._anki_btn.setText("Saved"))
        dlg.saved.connect(lambda: self._anki_btn.setEnabled(False))
        dlg.exec()


class SubtitleOverlay(QWidget):
    """Borderless, always-on-top bar showing the live subtitle + word cards."""

    _words_signal = Signal(list)
    _translation_signal = Signal(str)

    MARGIN_X = 24
    MARGIN_Y = 10

    def __init__(self, controller, get_source_lang=None, get_target_lang=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self._controller = controller
        self._get_src_lang = get_source_lang or (lambda: "en")
        self._get_tgt_lang = get_target_lang or (lambda: "en")

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.95)

        self._words_signal.connect(self._apply_words)
        self._translation_signal.connect(self._apply_translation)

        self._background = QFrame(self)
        self._background.setStyleSheet(
            f"background: {Theme.rgba(Theme.BG, 235)}; border-radius: 12px;"
        )

        self._flow_container = QWidget(self._background)
        self._lines_layout = QVBoxLayout(self._flow_container)
        self._lines_layout.setContentsMargins(0, 0, 0, 0)
        self._lines_layout.setSpacing(2)
        self._stable_width = min(
            int(QApplication.primaryScreen().geometry().width() * 0.8),
            760,
        )
        self._flow_container.setFixedWidth(self._stable_width - 2 * self.MARGIN_X)

        self._translation_label = QLabel(self._background)
        self._translation_label.setStyleSheet(
            f"color: {Theme.TRANSLATION_FG}; background: transparent; {Theme.font_css(Theme.FONT_TRANSLATION)}"
        )
        self._translation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._translation_label.setWordWrap(True)
        self._translation_label.hide()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._background)

        inner = QVBoxLayout(self._background)
        inner.setContentsMargins(self.MARGIN_X, self.MARGIN_Y, self.MARGIN_X, self.MARGIN_Y)
        inner.addWidget(self._flow_container)
        inner.addWidget(self._translation_label)

        self._hover_card = HoverCard(controller, self._get_src_lang, self._get_tgt_lang)
        self._hide_hover_timer = QTimer(self)
        self._hide_hover_timer.setSingleShot(True)
        self._hide_hover_timer.timeout.connect(self._hover_card.hide)

        self._words: list = []
        self._translation_text = ""
        self._translation_visible = False

        self._reposition()

    # ── public API (thread-safe) ──────────────────────────────────────
    def push_words(self, words: list):
        self._words_signal.emit(words)

    def push_translation(self, text: str):
        self._translation_signal.emit(text)

    def clear(self):
        self._words_signal.emit([])
        self._translation_signal.emit("")

    def set_translation_visible(self, visible: bool):
        self._translation_visible = visible
        self._translation_label.setVisible(visible and bool(self._translation_text))
        self._reposition()

    # ── slots (main thread only) ──────────────────────────────────────
    def _apply_words(self, words: list):
        self._words = words
        self._rebuild_word_labels()
        self._reposition()

    def _apply_translation(self, text: str):
        self._translation_text = text
        self._translation_label.setText(text)
        self._translation_label.setVisible(self._translation_visible and bool(text))
        self._reposition()

    def _rebuild_word_labels(self):
        while self._lines_layout.count():
            item = self._lines_layout.takeAt(0)
            row = item.layout()
            if row is not None:
                while row.count():
                    sub_item = row.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()
                row.deleteLater()
            elif item.widget():
                item.widget().deleteLater()

        if not self._words:
            return

        screen = QApplication.primaryScreen().geometry()
        max_line_width = self._stable_width - 2 * self.MARGIN_X
        metrics = QFontMetrics(WORD_FONT)
        word_pad = 12  # matches WordLabel's 6px horizontal padding on each side

        lines: list[list] = []
        current_line: list = []
        current_width = 0
        for word_obj in self._words:
            w_px = metrics.horizontalAdvance(word_obj.text) + word_pad
            if current_line and current_width + w_px > max_line_width:
                lines.append(current_line)
                current_line = []
                current_width = 0
            current_line.append(word_obj)
            current_width += w_px
        if current_line:
            lines.append(current_line)

        for line_words in lines:
            row = QHBoxLayout()
            row.setSpacing(4)
            for word_obj in line_words:
                lbl = WordLabel(word_obj)
                lbl.hovered.connect(self._on_word_hover)
                lbl.left.connect(self._on_word_leave)
                lbl.clicked.connect(self._on_word_click)
                row.addWidget(lbl)
            row.addStretch(1)
            self._lines_layout.addLayout(row)

    def _reposition(self):
        screen = QApplication.primaryScreen().geometry()
        self._stable_width = min(int(screen.width() * 0.8), 760)
        self._flow_container.setFixedWidth(self._stable_width - 2 * self.MARGIN_X)
        self._translation_label.setMaximumWidth(self._stable_width - 2 * self.MARGIN_X)

        self.setFixedWidth(self._stable_width)
        self.adjustSize()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + 60  # fixed distance from the top of the screen
        self.move(x, y)

    # ── hover / click handlers ─────────────────────────────────────────
    def _on_word_hover(self, word_obj, label: WordLabel):
        self._hide_hover_timer.stop()
        pos = label.mapToGlobal(QPoint(0, label.height() + 8))
        self._hover_card.show_for(word_obj, pos)

    def _on_word_leave(self):
        self._hide_hover_timer.start(150)

    def _on_word_click(self, word_obj):
        dlg = DetailDialog(self._controller, word_obj, self._get_src_lang(), parent=self)
        dlg.exec()
