"""Contract for a live audio source that can be polled for recent chunks."""

from abc import ABC, abstractmethod


class IAudioRecorder(ABC):
    @abstractmethod
    def start(self, filename: str | None = None):
        """Open the audio stream and begin buffering chunks."""
        raise NotImplementedError

    @abstractmethod
    def read_chunk(self) -> bytes:
        """Blocking read of one chunk from the stream (appends to internal buffer)."""
        raise NotImplementedError

    @abstractmethod
    def get_recent_chunks(self, seconds: float) -> list[bytes]:
        """Return raw PCM chunks (bytes) for the last N seconds."""
        raise NotImplementedError

    @abstractmethod
    def cleanup_and_save(self, save_wav: bool = True) -> str | None:
        """Release the stream/device and optionally persist the buffer to a WAV file."""
        raise NotImplementedError
