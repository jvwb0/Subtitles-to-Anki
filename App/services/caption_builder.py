"""
Groups transcribed words into readable, sentence-paced captions.

A caption is one sentence (or a bounded part of one, at most MAX_LINES lines)
that stays on screen until the next sentence starts or its reading time runs
out. Live partial words are shown on top of the committed (final) words but
are never committed themselves.
"""

import time
from typing import Callable

from models.word import Word

_SENTENCE_END = (".", "?", "!", "…")
_CLOSERS = "\"'”’)]»"


class CaptionBuilder:
    MAX_CHARS_PER_LINE  = 42
    MAX_LINES           = 2
    GAP_NEW_CAPTION_SEC = 1.2   # speech pause that starts a fresh caption
    MIN_HOLD_SEC        = 1.5   # shortest time a caption stays visible
    HOLD_PER_CHAR_SEC   = 0.05  # extra reading time per character

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._committed: list[Word] = []
        self._partial: list[Word] = []
        self._expires_at = 0.0

    # ── public API ───────────────────────────────────────────────────
    @property
    def max_chars(self) -> int:
        return self.MAX_CHARS_PER_LINE * self.MAX_LINES

    def add_final(self, words: list[Word]) -> bool:
        """Commit final words (they supersede any partial text).

        Returns True if they started a new caption.
        """
        self._partial = []
        restarted = False
        for word in words:
            if not word.text.strip():
                continue
            if self._committed and self._starts_new_caption(self._committed, word):
                self._committed = []
                restarted = True
            self._committed.append(word)
        if words:
            self._extend_hold()
        return restarted

    def set_partial(self, words: list[Word]):
        """Replace the live text of the segment still being spoken ([] clears it)."""
        self._partial = [w for w in words if w.text.strip()]
        if self._partial:
            self._extend_hold()

    def visible(self) -> list[Word]:
        """Words currently on screen; empty once the caption has expired."""
        if (self._committed or self._partial) and self._clock() >= self._expires_at:
            self.clear()
        return self._compose()[0]

    @property
    def shows_committed_caption(self) -> bool:
        """False while live text has already moved on to a new caption.

        A translation of the committed caption would then be stale.
        """
        return not self._compose()[1]

    def committed_text(self) -> str:
        return " ".join(w.text for w in self._committed)

    def clear(self):
        self._committed = []
        self._partial = []

    # ── internals ────────────────────────────────────────────────────
    def _compose(self) -> tuple[list[Word], bool]:
        shown = list(self._committed)
        restarted = False
        for word in self._partial:
            if shown and self._starts_new_caption(shown, word):
                shown = []
                restarted = True
            shown.append(word)
        return shown, restarted

    def _extend_hold(self):
        shown = self._compose()[0]
        hold = max(self.MIN_HOLD_SEC, self.HOLD_PER_CHAR_SEC * self._char_count(shown))
        self._expires_at = self._clock() + hold

    def _starts_new_caption(self, shown: list[Word], word: Word) -> bool:
        prev = shown[-1]
        if prev.text.rstrip(_CLOSERS).endswith(_SENTENCE_END):
            return True
        if word.startTime - prev.endTime > self.GAP_NEW_CAPTION_SEC:
            return True
        return self._char_count(shown) + 1 + len(word.text) > self.max_chars

    @staticmethod
    def _char_count(words: list[Word]) -> int:
        return sum(len(w.text) for w in words) + max(0, len(words) - 1)
