"""
Keeps every session recording in one folder with an auto-incrementing ID and
the settings in the file name, so runs can be compared later, e.g.

    0007_2026-10-25_2131_small_pt_gpu.wav
    0007_2026-10-25_2131_small_pt_gpu.txt   (final transcript with timestamps)
"""

import os
import re
import threading
from datetime import datetime

_DEFAULT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "recordings")
)
_ID_PATTERN = re.compile(r"^(\d+)_")


class RecordingStore:
    def __init__(self, directory: str = _DEFAULT_DIR):
        self.directory = directory
        self._lock = threading.Lock()

    def new_session_path(self, config, now: datetime | None = None) -> str:
        """Return the .wav path for the next session ID (the file itself is not created)."""
        os.makedirs(self.directory, exist_ok=True)
        stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M")
        with self._lock:
            name = f"{self._next_id():04d}_{stamp}_{self._describe(config)}.wav"
        return os.path.join(self.directory, name)

    def _next_id(self) -> int:
        ids = [
            int(m.group(1))
            for name in os.listdir(self.directory)
            if (m := _ID_PATTERN.match(name))
        ]
        return max(ids, default=0) + 1

    @staticmethod
    def _describe(config) -> str:
        device = "gpu" if config.use_gpu else "cpu"
        return f"{config.model_size}_{config.language}_{device}"

    @staticmethod
    def transcript_path(wav_path: str) -> str:
        return os.path.splitext(wav_path)[0] + ".txt"

    def write_transcript(self, wav_path: str, lines: list[str]):
        with open(self.transcript_path(wav_path), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
