# live_transcriber.py
"""
Rolling-window live transcription with robust deduplication.

The core problem: we re-transcribe a largely-overlapping audio window
every tick.  Whisper returns the same words each time but with:
  - slightly different timestamps (+-0.3-0.5 s)
  - different punctuation on the same word ("that" / "that," / "that.")
  - occasionally different spellings ("rectify" / "rectify.")

Dedup strategy (layered, each one catches what the others miss):
  1. Absolute-time cutoff   - skip anything ending before lastEmittedEnd + grace
  2. Punctuation-stripped text match - the emitted-text history stores
     keys with ALL punctuation removed, so "that," == "that." == "that"
  3. N-gram sequence guard  - even if individual words slip through,
     if the last N emitted words match the first N words of the new batch,
     we know the batch is a stale re-run and strip the overlap off the front
"""

import re
from models.word import Word
from services.audio_conversion import AudioConverter


def _strip_punct(text: str) -> str:
    """Lower-case + remove all punctuation + collapse whitespace."""
    return re.sub(r'[^\w\s]', '', text.lower()).strip()


class LiveTranscriber:
    # ── tuning knobs ─────────────────────────────────────────────────
    TIME_GRACE_SEC   = 0.30   # how far past lastEmittedEnd a word can land
                              # and still be considered "old"  (whisper jitter)
    DEDUP_WINDOW_SEC = 3.0    # how far back in time we keep emitted-text history
    NGRAM_N          = 3      # how many trailing words to compare for sequence guard

    def __init__(self, whisper, recorder, language: str = "en"):
        """
        whisper   – WhisperService instance (owns the model + tuned params)
        recorder  – AudioCaptureLive instance
        """
        self.whisper  = whisper
        self.recorder = recorder
        self.language = language
        self.reset()

    def reset(self):
        self.lastEmittedEnd  = 0.0
        # history: list of (abs_end_time, stripped_key)
        self._emitted: list[tuple[float, str]] = []
        # trailing-word ring for n-gram guard (stripped keys, in order)
        self._tail: list[str] = []

    # ── main tick ────────────────────────────────────────────────────
    def tick(self, windowSec: float = 2.0) -> list[Word]:
        chunks = self.recorder.getRecentChunks(windowSec)
        if not chunks:
            return []

        audio = AudioConverter.chunks_to_float_mono_16k(
            chunks,
            srcRate=self.recorder.rate,
            channels=self.recorder.channels,
        )
        if audio.size == 0:
            return []

        words = self.whisper.transcribe(audio, self.language)
        if not words:
            return []

        # ── 1. shift to absolute timestamps ──────────────────────────
        total_chunks  = len(self.recorder.frames)
        recorded_sec  = (total_chunks * self.recorder.chunk) / self.recorder.rate
        window_start  = max(0.0, recorded_sec - windowSec)

        for w in words:
            w.startTime += window_start
            w.endTime   += window_start

        # ── 2. n-gram sequence guard (strip stale prefix) ───────────
        words = self._strip_ngram_prefix(words)
        if not words:
            return []

        # ── 3. per-word filtering ────────────────────────────────────
        new_words: list[Word] = []

        for w in words:
            key = _strip_punct(w.text)
            if not key:
                continue

            # (a) absolute-time cutoff
            if w.endTime <= self.lastEmittedEnd + self.TIME_GRACE_SEC:
                continue

            # (b) text-proximity dedup against recent history
            if self._seen_recently(key, w.startTime):
                continue

            new_words.append(w)

        # ── 4. commit ────────────────────────────────────────────────
        if new_words:
            self.lastEmittedEnd = new_words[-1].endTime

            for w in new_words:
                key = _strip_punct(w.text)
                self._emitted.append((w.endTime, key))
                self._tail.append(key)
                if len(self._tail) > self.NGRAM_N:
                    self._tail = self._tail[-self.NGRAM_N:]

            # prune old history
            cutoff = self.lastEmittedEnd - self.DEDUP_WINDOW_SEC - 1.0
            self._emitted = [(t, k) for t, k in self._emitted if t > cutoff]

        return new_words

    # ── helpers ──────────────────────────────────────────────────────
    def _seen_recently(self, key: str, word_start: float) -> bool:
        """True if key appears in emitted history within DEDUP_WINDOW_SEC."""
        for (prev_end, prev_key) in self._emitted:
            if word_start - prev_end > self.DEDUP_WINDOW_SEC:
                continue
            if key == prev_key:
                return True
        return False

    def _strip_ngram_prefix(self, words: list[Word]) -> list[Word]:
        """
        If the leading words of `words` (stripped) match self._tail,
        remove them - they are a stale re-run of what we already emitted.

        Example:
          _tail       = ["close", "bond", "bond"]   (last 3 emitted)
          new words   = ["close", "bond", "bond", "with", "her"]
          -> strip first 3 -> return ["with", "her"]
        """
        if not self._tail or not words:
            return words

        n = min(self.NGRAM_N, len(self._tail), len(words))
        tail_slice  = self._tail[-n:]
        words_slice = [_strip_punct(w.text) for w in words[:n]]

        if tail_slice == words_slice:
            return words[n:]
        return words