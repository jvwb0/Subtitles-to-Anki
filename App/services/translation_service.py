# services/translation_service.py
"""
Async sentence-level translation using deep-translator (GoogleTranslator).
Debounces rapid calls so Google Translate is not spammed on every word.
"""

import threading
from deep_translator import GoogleTranslator


class TranslationService:
    """Translate sentence text asynchronously with debouncing."""

    DEBOUNCE_SEC = 0.6

    def __init__(self):
        self._source_lang = "auto"
        self._lock = threading.Lock()
        self._pending_text: str | None = None
        self._pending_callback = None
        self._timer: threading.Timer | None = None
        self._last_translated_text: str = ""
        self._last_translation: str = ""

    def set_source_lang(self, lang_code: str):
        """Update source language. 'auto' for auto-detect."""
        with self._lock:
            self._source_lang = lang_code if lang_code != "en" else "auto"

    def translate_async(self, text: str, callback):
        """Request translation of *text*.  Debounced: only the last call
        within DEBOUNCE_SEC actually fires.
        ``callback(translated_str)`` is called on a background thread."""
        with self._lock:
            self._pending_text = text
            self._pending_callback = callback

            if self._timer is not None:
                self._timer.cancel()

            # Return cached result immediately if text unchanged
            if text.strip() == self._last_translated_text:
                cb, cached = callback, self._last_translation
                threading.Thread(target=lambda: cb(cached), daemon=True).start()
                return

            self._timer = threading.Timer(self.DEBOUNCE_SEC, self._do_translate)
            self._timer.daemon = True
            self._timer.start()

    def _do_translate(self):
        with self._lock:
            text = self._pending_text
            callback = self._pending_callback
            src = self._source_lang
            if text is None or callback is None:
                return

        from services.cache_service import CacheService
        cached = CacheService.get().get_translation(text, src, "en")
        if cached:
            with self._lock:
                self._last_translated_text = text.strip()
                self._last_translation = cached
            callback(cached)
            return

        try:
            result = GoogleTranslator(source=src, target="en").translate(text)
            if result:
                with self._lock:
                    self._last_translated_text = text.strip()
                    self._last_translation = result
                CacheService.get().save_translation(text, src, "en", result)
                callback(result)
        except Exception as e:
            print(f"Translation error: {e}")

    def clear(self):
        """Reset state (e.g. when feature is toggled off)."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending_text = None
            self._pending_callback = None
            self._last_translated_text = ""
            self._last_translation = ""
