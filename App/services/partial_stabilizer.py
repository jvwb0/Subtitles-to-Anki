"""
Keeps live (partial) captions from flickering.

Whisper re-reads the open segment every few hundred ms and may reword earlier
parts each time. A word is *locked* once two consecutive hypotheses agree on
it; locked words never change again until the segment ends. Only the unstable
tail (always at least the newest word) is allowed to move.
"""

from models.word import Word
from utils.text_utils import strip_punct


class PartialStabilizer:
    TIME_TOLERANCE_SEC = 0.15  # overlap allowed when re-aligning by timestamp

    def __init__(self):
        self.reset()

    def reset(self):
        self._locked: list[Word] = []
        self._previous_tail: list[Word] = []

    def update(self, hypothesis: list[Word]) -> list[Word]:
        """Takes the newest hypothesis and returns the words to display."""
        tail = self._tail_after_locked(hypothesis)

        # Never lock the newest word: it is the one most likely still forming.
        lockable = min(self._common_prefix_len(self._previous_tail, tail), len(tail) - 1)
        if lockable > 0:
            self._locked.extend(tail[:lockable])
            tail = tail[lockable:]

        self._previous_tail = tail
        return self._locked + tail

    def _tail_after_locked(self, hypothesis: list[Word]) -> list[Word]:
        n = len(self._locked)
        if n == 0:
            return list(hypothesis)
        if self._same_words(self._locked, hypothesis[:n]):
            return list(hypothesis[n:])
        # The hypothesis reworded locked text: keep ours, align the rest by time.
        locked_end = self._locked[-1].endTime
        return [w for w in hypothesis if w.startTime >= locked_end - self.TIME_TOLERANCE_SEC]

    @staticmethod
    def _same_words(a: list[Word], b: list[Word]) -> bool:
        return len(a) == len(b) and all(strip_punct(x.text) == strip_punct(y.text) for x, y in zip(a, b))

    @staticmethod
    def _common_prefix_len(a: list[Word], b: list[Word]) -> int:
        count = 0
        for x, y in zip(a, b):
            if strip_punct(x.text) != strip_punct(y.text):
                break
            count += 1
        return count
