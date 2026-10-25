"""Contract for asynchronous, debounced sentence translation."""

from abc import ABC, abstractmethod


class ITranslationProvider(ABC):
    @abstractmethod
    def set_source_lang(self, lang_code: str):
        raise NotImplementedError

    @abstractmethod
    def translate_async(self, text: str, callback):
        """Debounced translate; `callback(translated_str)` fires on a BG thread."""
        raise NotImplementedError

    @abstractmethod
    def clear(self):
        """Reset pending/cached state (e.g. when the feature is toggled off)."""
        raise NotImplementedError
