# controllers/app_controller.py
"""
Facade that composes the focused sub-controllers below. Views only ever
talk to AppController — it exists so views don't need to know which
sub-controller owns which feature.

    TranscriptionController  — Whisper/VAD/audio lifecycle + live sessions
    DefinitionController     — dictionary lookups (hover/click cards)
    AnkiController           — deck/note CRUD via AnkiConnect
    TranslationController    — dual-subtitle (original + English) translation
"""

from controllers.transcription_controller import TranscriptionController
from controllers.definition_controller import DefinitionController
from controllers.anki_controller import AnkiController
from controllers.translation_controller import TranslationController
from services.anki_service import AnkiService
from services.definition_service import DefinitionService


class AppController:
    """Central controller — always available for definition/Anki,
    transcription loaded on demand via load_transcription()."""

    def __init__(self):
        self._transcription = TranscriptionController()
        self._definitions = DefinitionController(DefinitionService())
        self._anki = AnkiController(AnkiService())
        self._translation = TranslationController()

    # ==================================================================
    # Transcription lifecycle
    # ==================================================================

    def load_transcription(self, config):
        self._transcription.load(config)

    def unload_transcription(self):
        self._transcription.unload()

    @property
    def is_transcription_loaded(self) -> bool:
        return self._transcription.is_loaded

    @property
    def is_recording(self) -> bool:
        return self._transcription.is_recording

    def set_translate(self, enabled: bool):
        """Toggle Whisper translate mode (any language → English) at runtime."""
        self._transcription.set_translate(enabled)

    def start_live_background(self, on_words_callback=None, on_partial_callback=None):
        """Live transcription with final words and live partial text."""
        self._transcription.start_background(
            on_words_callback=on_words_callback,
            on_partial_callback=on_partial_callback,
        )

    def stop_live_background(self, save_wav=True):
        return self._transcription.stop_background(save_wav=save_wav)

    # ==================================================================
    # Dual subtitle (original + English translation)
    # ==================================================================

    @property
    def is_dual_subtitle_enabled(self) -> bool:
        return self._translation.is_enabled

    def set_dual_subtitle(self, enabled: bool):
        """Toggle dual-subtitle mode (show original + English translation)."""
        self._translation.set_enabled(enabled)

    def translate_subtitle(self, text: str, source_lang: str, callback):
        """Translate subtitle text asynchronously.
        callback(translated_text) called on a BG thread."""
        self._translation.translate(text, source_lang, callback)

    # ==================================================================
    # Definition methods  (always available, no model needed)
    # ==================================================================

    def fetch_hover_definition(self, word, src_lang, tgt_lang, on_ready):
        self._definitions.fetch_hover_definition(word, src_lang, tgt_lang, on_ready)

    def fetch_full_definition(self, word, src_lang, tgt_lang, on_ready):
        self._definitions.fetch_full_definition(word, src_lang, tgt_lang, on_ready)

    # ==================================================================
    # Anki methods  (always available, no model needed)
    # ==================================================================

    def ensure_anki_ready(self, on_ready):
        self._anki.ensure_anki_ready(on_ready)

    def create_anki_deck(self, name, on_ready):
        self._anki.create_anki_deck(name, on_ready)

    def save_to_anki(self, word, deck_name, src_lang, on_ready):
        self._anki.save_to_anki(word, deck_name, src_lang, on_ready)
