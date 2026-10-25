"""
Chooses where to cut a long stretch of continuous speech.

Instead of cutting blindly after N seconds, cut at the most natural boundary
Whisper found: a real pause between words, preferably after sentence or clause
punctuation. Words after the cut stay open and are transcribed again with the
next segment.
"""

from models.word import Word

_SENTENCE_END = (".", "?", "!", "…")
_CLAUSE_END = (",", ";", ":", "—", "-")
_CLOSERS = "\"'”’)]»"


class SegmentSplitter:
    MIN_FINAL_SEC = 1.5     # don't cut off a tiny fragment
    SENTENCE_BONUS = 0.6    # seconds-equivalent preference for ending on . ? !
    CLAUSE_BONUS = 0.25     # ... and for ending on , ; :

    @classmethod
    def split_index(cls, words: list[Word], stable_end: float) -> int | None:
        """How many leading words to finalize, or None when no safe boundary exists.

        Only words that end by `stable_end` qualify; later ones may still change.
        Ties go to the later boundary so as much text as possible is finalized.
        """
        best_count, best_score = None, float("-inf")
        for i, word in enumerate(words):
            if word.endTime > stable_end:
                break
            if word.endTime - words[0].startTime < cls.MIN_FINAL_SEC:
                continue
            following = words[i + 1] if i + 1 < len(words) else None
            gap = following.startTime - word.endTime if following else 0.0
            score = gap + cls._punctuation_bonus(word.text)
            if score >= best_score:
                best_count, best_score = i + 1, score
        return best_count

    @classmethod
    def _punctuation_bonus(cls, text: str) -> float:
        text = text.rstrip(_CLOSERS)
        if text.endswith(_SENTENCE_END):
            return cls.SENTENCE_BONUS
        if text.endswith(_CLAUSE_END):
            return cls.CLAUSE_BONUS
        return 0.0
