# controllers/translation_controller.py
"""Dual-subtitle (original + English) translation, lazily backed by TranslationService."""

from interfaces.translation_provider import ITranslationProvider


class TranslationController:
    def __init__(self):
        self._enabled = False
        self._provider: ITranslationProvider | None = None  # lazy init

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if not enabled and self._provider:
            self._provider.clear()

    def translate(self, text: str, source_lang: str, callback):
        """Translate subtitle text asynchronously.
        callback(translated_text) called on a BG thread."""
        if not self._enabled:
            return
        if self._provider is None:
            from services.translation_service import TranslationService
            self._provider = TranslationService()
        self._provider.set_source_lang(source_lang)
        self._provider.translate_async(text, callback)
