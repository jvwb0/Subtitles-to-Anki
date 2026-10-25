"""Contract for looking up word definitions/grammar from a dictionary source."""

from abc import ABC, abstractmethod


class IDefinitionProvider(ABC):
    @abstractmethod
    def fetch_definition(self, word: str, source_lang: str, target_lang: str) -> dict:
        """Short definition + part of speech, for hover cards."""
        raise NotImplementedError

    @abstractmethod
    def fetch_details(self, word: str, source_lang: str, target_lang: str) -> dict:
        """Full entry (senses, forms, pronunciations), for pinned detail cards."""
        raise NotImplementedError
