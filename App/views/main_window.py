# views/main_window.py
"""Main control window: device/model/language selection, start/stop, transcript log."""

import gc

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QCheckBox, QPushButton, QTextEdit, QSizePolicy,
)

from controllers.app_controller import AppController
from models.config import TranscriptionConfig
from models.reference_data import LANGUAGES, MODEL_INFO
from services.audio_device_service import AudioDeviceService
from utils.app_logger import get_logger
from views.native_effects import apply_windows_backdrop
from views.subtitle_overlay import SubtitleOverlay
from views.theme import Theme

logger = get_logger(__name__)
MAX_TRANSCRIPT_CHARS = 20_000  # cap so the widget can't grow unbounded over a long session
MAX_SUBTITLE_WORDS = 10


class MainWindow(QMainWindow):
    # Background threads (transcription loop) emit through this signal;
    # Qt automatically queues the delivery onto the GUI thread.
    _words_ready = Signal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Transcriber")
        self.resize(640, 720)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.controller = AppController()
        self.overlay = SubtitleOverlay(self.controller, get_source_lang=self._get_transcription_lang)

        self.is_running = False
        self.model_loaded = False
        self._subtitle_buffer: list = []
        self._transcript_chars = 0

        self._words_ready.connect(self._on_words_main_thread)

        self._has_psutil = False
        try:
            import psutil
            self._psutil_process = psutil.Process()
            self._has_psutil = True
        except ImportError:
            pass

        self._build_ui()
        self._refresh_devices()
        apply_windows_backdrop(self, dark=Theme.IS_DARK)

        if self._has_psutil:
            self._ram_timer = QTimer(self)
            self._ram_timer.timeout.connect(self._update_ram_label)
            self._ram_timer.start(2000)

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background: {Theme.rgba(Theme.WINDOW_BG, 242)};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addLayout(self._build_settings_grid())
        root.addLayout(self._build_action_buttons())
        root.addLayout(self._build_status_row())
        root.addWidget(self._build_transcript_box())

        footer = QLabel("💡 Audio buffer capped at 5 min (~65 MB RAM) — safe for long recordings")
        footer.setProperty("role", "muted")
        root.addWidget(footer)

    def _build_settings_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        # ── device ─────────────────────────────────────────────────
        grid.addWidget(QLabel("Loopback device:"), 0, 0)
        self.device_combo = QComboBox()
        grid.addWidget(self.device_combo, 0, 1, 1, 2)
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(36)
        refresh_btn.setToolTip("Re-scan audio devices\n(use if you plug in new hardware)")
        refresh_btn.clicked.connect(self._refresh_devices)
        grid.addWidget(refresh_btn, 0, 3)

        # ── model + language ─────────────────────────────────────────
        grid.addWidget(QLabel("Model:"), 1, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(list(MODEL_INFO.keys()))
        self.model_combo.setCurrentText("small")
        self.model_combo.currentTextChanged.connect(self._on_model_select)
        grid.addWidget(self.model_combo, 1, 1)

        self.model_info_label = QLabel(MODEL_INFO["small"])
        self.model_info_label.setProperty("role", "muted")
        grid.addWidget(self.model_info_label, 2, 1, 1, 2)

        grid.addWidget(QLabel("Language:"), 1, 2)
        self.lang_combo = QComboBox()
        for name, code in LANGUAGES:
            self.lang_combo.addItem(f"{name} ({code})", code)
        grid.addWidget(self.lang_combo, 1, 3)

        # ── GPU + WAV save ────────────────────────────────────────────
        self.gpu_check = QCheckBox("Use GPU (CUDA)")
        self.gpu_check.setChecked(True)
        self.gpu_check.setToolTip("Uses float16 on GPU when available, falls back to CPU otherwise")
        grid.addWidget(self.gpu_check, 3, 0, 1, 2)

        self.save_wav_check = QCheckBox("Save recording to WAV")
        self.save_wav_check.setToolTip("Save last 5 min of audio to disk after stopping\n(buffer is capped, no RAM impact)")
        grid.addWidget(self.save_wav_check, 3, 2, 1, 2)

        # ── mode + translate ──────────────────────────────────────────
        grid.addWidget(QLabel("Mode:"), 4, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Fast (300ms, quick response)",
            "VAD (pause detection, lowest resource use)",
            "Accurate (700ms, continuous speech)",
        ])
        self.mode_combo.setCurrentIndex(1)  # default to VAD — lowest CPU/GPU load for long sessions
        grid.addWidget(self.mode_combo, 4, 1, 1, 2)

        self.translate_check = QCheckBox("Translate → EN")
        self.translate_check.setToolTip("Translate foreign speech to English subtitles\n(uses Whisper's built-in translation)")
        self.translate_check.toggled.connect(self._on_translate_toggle)
        grid.addWidget(self.translate_check, 4, 3)

        self.dual_sub_check = QCheckBox("Show Translation (EN)")
        self.dual_sub_check.setToolTip("Show English translation below the original subtitles\n(uses Google Translate — requires internet)")
        self.dual_sub_check.toggled.connect(self._on_dual_subtitle_toggle)
        grid.addWidget(self.dual_sub_check, 5, 1, 1, 2)

        grid.setColumnStretch(1, 1)
        return grid

    def _build_action_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.load_btn = QPushButton("Load Model")
        self.load_btn.setProperty("variant", "primary")
        self.load_btn.clicked.connect(self._load_model)
        row.addWidget(self.load_btn)

        self.start_btn = QPushButton("Start")
        self.start_btn.setProperty("variant", "success")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setProperty("variant", "danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        row.addWidget(self.stop_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Clear transcript text and subtitle overlay")
        clear_btn.clicked.connect(self._clear)
        row.addWidget(clear_btn)

        self.unload_btn = QPushButton("Unload Model")
        self.unload_btn.setToolTip("Free VRAM/RAM by unloading Whisper model\n(must reload before starting again)")
        self.unload_btn.setEnabled(False)
        self.unload_btn.clicked.connect(self._unload_model)
        row.addWidget(self.unload_btn)

        row.addStretch(1)
        return row

    def _build_status_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.status_label = QLabel("Idle")
        self.status_label.setProperty("role", "status")
        row.addWidget(self.status_label)
        row.addStretch(1)

        if self._has_psutil:
            self.ram_label = QLabel("RAM: — MB")
            self.ram_label.setProperty("role", "muted")
            row.addWidget(self.ram_label)
        else:
            note = QLabel("(install psutil for RAM monitor)")
            note.setProperty("role", "muted")
            row.addWidget(note)
        return row

    def _build_transcript_box(self) -> QTextEdit:
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return self.transcript

    # ==================================================================
    # Getters (grouped together)
    # ==================================================================

    def _get_transcription_lang(self) -> str:
        return self.lang_combo.currentData() or "en"

    # ==================================================================
    # Device list
    # ==================================================================

    def _refresh_devices(self):
        self._devices = AudioDeviceService.list_loopback_devices()
        self.device_combo.clear()
        for idx, name in self._devices:
            self.device_combo.addItem(f"[{idx}] {name}", idx)
        if not self._devices:
            self.device_combo.addItem("No WASAPI loopback devices found", None)

    # ==================================================================
    # RAM monitor
    # ==================================================================

    def _update_ram_label(self):
        try:
            mem_mb = self._psutil_process.memory_info().rss / 1024 / 1024
            self.ram_label.setText(f"RAM: {mem_mb:.0f} MB")
        except Exception:
            self.ram_label.setText("RAM: —")

    # ==================================================================
    # Toggles
    # ==================================================================

    def _on_model_select(self, model: str):
        self.model_info_label.setText(MODEL_INFO.get(model, ""))

    def _on_translate_toggle(self, enabled: bool):
        if enabled:
            self.dual_sub_check.setChecked(False)  # mutually exclusive with dual subtitle
            self.overlay.set_translation_visible(False)
        self.controller.set_translate(enabled)

    def _on_dual_subtitle_toggle(self, enabled: bool):
        if enabled:
            self.translate_check.setChecked(False)  # mutually exclusive with Whisper translate
        self.controller.set_dual_subtitle(enabled)
        self.overlay.set_translation_visible(enabled)

    # ==================================================================
    # Model load / unload
    # ==================================================================

    def _load_model(self):
        if self.model_loaded:
            self.status_label.setText("Model already loaded ✓")
            return

        device_id = self.device_combo.currentData()
        if device_id is None:
            self.status_label.setText("Select a valid audio device first")
            return

        config = TranscriptionConfig(
            model_size=self.model_combo.currentText(),
            device_id=device_id,
            use_gpu=self.gpu_check.isChecked(),
            language=self._get_transcription_lang(),
        )

        self.status_label.setText("Loading model…")
        self.repaint()

        try:
            self.controller.load_transcription(config)
            self.model_loaded = True
            self.status_label.setText("Model loaded ✓  Ready")
            self.start_btn.setEnabled(True)
            self.unload_btn.setEnabled(True)
        except Exception as e:
            logger.exception("Failed to load transcription model")
            self.status_label.setText(f"Error loading model: {e}")
            self.model_loaded = False

    def _unload_model(self):
        if not self.model_loaded or self.is_running:
            self.status_label.setText("Stop transcription first")
            return

        self.controller.unload_transcription()
        self.model_loaded = False
        self.start_btn.setEnabled(False)
        self.unload_btn.setEnabled(False)
        self.status_label.setText("Model unloaded — VRAM freed")
        gc.collect()

    # ==================================================================
    # Start / stop
    # ==================================================================

    def _start(self):
        if not self.model_loaded or not self.controller.is_transcription_loaded or self.is_running:
            return

        self.is_running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.unload_btn.setEnabled(False)
        self.status_label.setText("Recording…")
        self.overlay.show()

        mode_map = {0: "fast", 1: "vad", 2: "accurate"}
        mode = mode_map[self.mode_combo.currentIndex()]
        self.controller.start_live_background(on_words_callback=self._on_words, mode=mode)

    def _stop(self):
        if not self.is_running:
            return
        self.status_label.setText("Stopping…")
        if self.controller.is_transcription_loaded:
            self.controller.stop_live_background(save_wav=self.save_wav_check.isChecked())
        self.is_running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.unload_btn.setEnabled(True)
        self.status_label.setText("Idle")
        self.overlay.hide()

    # ==================================================================
    # Word callback (background thread) → main-thread slot
    # ==================================================================

    def _on_words(self, words):
        """Called on the transcription background thread — never touch widgets here."""
        self._words_ready.emit(words)

    def _on_words_main_thread(self, words):
        try:
            self._process_new_words(words)
        except Exception:
            logger.exception("Failed to process new transcribed words")

    def _process_new_words(self, words):
        new_words = [w for w in words if w.text.strip()]
        if not new_words:
            return

        self._subtitle_buffer.extend(new_words)
        self._subtitle_buffer = self._subtitle_buffer[-MAX_SUBTITLE_WORDS:]

        self.overlay.push_words(list(self._subtitle_buffer))
        self._append_transcript(" ".join(w.text for w in new_words))

        if self.controller.is_dual_subtitle_enabled:
            sentence = " ".join(w.text for w in self._subtitle_buffer)
            src_lang = self._get_transcription_lang()
            self.controller.translate_subtitle(
                sentence, src_lang,
                callback=lambda translated: self.overlay.push_translation(translated),
            )

    def _append_transcript(self, text: str):
        chunk = text + " "
        cursor = self.transcript.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(chunk)
        self._transcript_chars += len(chunk)
        self._trim_transcript()
        self.transcript.ensureCursorVisible()

    def _trim_transcript(self):
        overflow = self._transcript_chars - MAX_TRANSCRIPT_CHARS
        if overflow <= 0:
            return
        cursor = self.transcript.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        cursor.movePosition(cursor.MoveOperation.Right, cursor.MoveMode.KeepAnchor, overflow)
        cursor.removeSelectedText()
        self._transcript_chars -= overflow

    # ==================================================================
    # Misc
    # ==================================================================

    def _clear(self):
        self.transcript.clear()
        self._transcript_chars = 0
        self._subtitle_buffer.clear()
        self.overlay.clear()

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)
