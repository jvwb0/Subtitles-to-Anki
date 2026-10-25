"""Contract for talking to a running Anki instance via AnkiConnect."""

from abc import ABC, abstractmethod


class IAnkiGateway(ABC):
    # ── connection lifecycle ──────────────────────────────────────────
    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def ensure_running(self, timeout: float = 15.0) -> bool:
        """Launch Anki if needed and wait until AnkiConnect responds."""
        raise NotImplementedError

    # ── deck CRUD ──────────────────────────────────────────────────────
    @abstractmethod
    def get_deck_names(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def create_deck(self, deck_name: str) -> dict:
        raise NotImplementedError

    # ── note CRUD ────────────────────────────────────────────────────
    @abstractmethod
    def add_note(self, deck_name: str, fields: dict) -> dict:
        raise NotImplementedError
