"""Contract for the persistent definition/translation cache."""

from abc import ABC, abstractmethod


class ICacheRepository(ABC):
    # ── definitions ──────────────────────────────────────────────────
    @abstractmethod
    def get_definition(self, word: str, lang: str) -> tuple:
        raise NotImplementedError

    @abstractmethod
    def save_simple(self, word: str, lang: str, result: dict):
        raise NotImplementedError

    @abstractmethod
    def save_detail(self, word: str, lang: str, result: dict):
        raise NotImplementedError

    # ── translations ─────────────────────────────────────────────────
    @abstractmethod
    def get_translation(self, text: str, src: str, tgt: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def save_translation(self, text: str, src: str, tgt: str, result: str):
        raise NotImplementedError
