"""Contract for anything that turns raw audio into a list of `Word`s."""

from abc import ABC, abstractmethod

from models.word import Word


class ITranscriptionEngine(ABC):
    @abstractmethod
    def transcribe(self, audio, language: str = "en", task: str = "transcribe",
                   prompt: str | None = None) -> list[Word]:
        """Transcribe a float32 16kHz mono numpy array into timestamped words.

        `prompt` is the text just before this audio; it steers punctuation,
        casing and vocabulary so consecutive segments read consistently.
        """
        raise NotImplementedError
