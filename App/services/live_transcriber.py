# services/live_transcriber_provisional.py
"""
Live transcriber with provisional word support and revision tracking.

Features:
- Emits words immediately (may be provisional)
- Re-transcribes overlapping audio
- Detects revisions and confirms words
- Sends update events for changed words
"""

from typing import List, Tuple, Optional
from models.word import Word, WordState
from services.audio_conversion import AudioConverter
from utils.text_utils import strip_punct as _strip_punct


class LiveTranscriber:  # KEPT SAME NAME
    """Live transcriber with provisional word support."""
    # ── tuning knobs ─────────────────────────────────────────────────
    TIME_GRACE_SEC   = 0.10   # REDUCED: timestamp jitter tolerance (was 0.30)
    DEDUP_WINDOW_SEC = 1.5    # REDUCED: text dedup window (was 4.0)
    NGRAM_N          = 2      # REDUCED: n-gram overlap (was 4)

    # Confidence thresholds
    MIN_WORD_PROB    = 0.55
    MIN_AVG_LOGPROB_CONFIRMED = Word.LOGPROB_THRESHOLD  # Above this → confirmed
    MIN_AVG_LOGPROB_EMIT = -0.55       # Above this → emit as provisional
    MAX_NO_SPEECH_PROB = 0.70  # INCREASED: allow more (was 0.65)

    TIME_BUCKET_SEC = 0.30
    MIN_WORD_LENGTH = 2

    # Revision settings
    REVISION_WINDOW_SEC = 2.5  # REDUCED: revision check window (was 3.0)
    MIN_OVERLAP_RATIO = 0.6    # INCREASED: stricter overlap check (was 0.5)
    
    # Whitelist of valid short words
    COMMON_SHORT_WORDS = frozenset({
        'in', 'to', 'of', 'is', 'it', 'on', 'at', 'by', 'or', 'if',
        'we', 'he', 'me', 'my', 'so', 'no', 'up', 'do', 'go', 'be',
        'an', 'as', 'am', 'i', 'a'
    })

    def __init__(self, whisper, recorder, vad=None, language: str = "en",
                 task: str = "transcribe"):
        """
        Args:
            whisper: WhisperService instance
            recorder: AudioCaptureLive instance
            vad: VadService instance (optional, not used in streaming mode)
            language: Language code for transcription
            task: "transcribe" or "translate" (translate → English)
        """
        self.whisper  = whisper
        self.recorder = recorder
        self.vad      = vad  # Kept for API compatibility, not used in streaming mode
        self.language = language
        self.task     = task
        self.reset()

    def reset(self):
        self.lastEmittedEnd  = 0.0
        self._displayed_words: List[Word] = []  # Track words currently displayed
        self._tail: list[str] = []  # For n-gram dedup

    # ── main tick ────────────────────────────────────────────────────
    def tick(self, windowSec: float = 3.0) -> Tuple[List[Word], List[Tuple[Word, Word]]]:
        """
        Transcribe recent audio with provisional word support.
        
        Returns:
            (new_words, revisions)
            new_words: List of newly emitted words
            revisions: List of (old_word, new_word) tuples for words that changed
        """
        chunks = self.recorder.getRecentChunks(windowSec)
        if not chunks:
            return [], []

        audio = AudioConverter.chunks_to_float_mono_16k(
            chunks,
            srcRate=self.recorder.rate,
            channels=self.recorder.channels,
        )
        if audio.size == 0:
            return [], []

        # ── 1. Transcribe ────────────────────────────────────────────
        total_chunks = len(self.recorder.frames)
        recorded_sec = (total_chunks * self.recorder.chunk) / self.recorder.rate
        window_start = max(0.0, recorded_sec - windowSec)

        words = self.whisper.transcribe(audio, self.language, task=self.task)
        if not words:
            return [], []

        # Adjust to absolute timestamps
        for w in words:
            w.startTime += window_start
            w.endTime += window_start

        # ── 2. Strip n-gram prefix (old dedup) ──────────────────────
        words = self._strip_ngram_prefix(words)
        if not words:
            return [], []

        # ── 3. Check for revisions ───────────────────────────────────
        revisions = []
        truly_new_words = []
        
        for w in words:
            key = _strip_punct(w.text)
            if not key:
                continue
            
            # Filter fragments
            if len(key) < self.MIN_WORD_LENGTH and key not in self.COMMON_SHORT_WORDS:
                continue
            
            # Skip silence
            if w.no_speech_prob is not None and w.no_speech_prob >= self.MAX_NO_SPEECH_PROB:
                continue
            
            # Check if this word overlaps with a provisional word
            overlapping = self._find_overlapping_word(w)
            
            if overlapping and overlapping.is_provisional:
                # Check if text changed
                if _strip_punct(overlapping.text) != key:
                    # Word was revised!
                    w.mark_revised()
                    revisions.append((overlapping, w))
                    self._replace_displayed_word(overlapping, w)
                else:
                    # Same word, check if confidence improved
                    if self._is_better_confidence(w, overlapping):
                        # Confirm the word
                        overlapping.confirm()
                        # Update confidence scores
                        overlapping.avg_logprob = w.avg_logprob
                        overlapping.confidence = w.confidence
            else:
                # Check if this is truly new (not already displayed)
                if not self._is_already_displayed(w):
                    truly_new_words.append(w)
        
        # ── 4. Filter truly new words (minimal dedup for streaming) ──
        filtered_new = []
        for w in truly_new_words:
            # REMOVED aggressive time cutoff - rely on text-based dedup instead
            # In streaming mode, timestamps can overlap between ticks

            # Text-proximity dedup (same word text recently?)
            key = _strip_punct(w.text)
            if self._seen_recently(key, w.startTime):
                continue

            filtered_new.append(w)
        
        # ── 5. Update tracking ───────────────────────────────────────
        if filtered_new:
            self.lastEmittedEnd = filtered_new[-1].endTime
            
            # Add to displayed words
            self._displayed_words.extend(filtered_new)
            
            # Update tail for n-gram
            for w in filtered_new:
                key = _strip_punct(w.text)
                self._tail.append(key)
                if len(self._tail) > self.NGRAM_N:
                    self._tail = self._tail[-self.NGRAM_N:]
        
        # Prune old displayed words (keep last REVISION_WINDOW_SEC)
        cutoff_time = recorded_sec - self.REVISION_WINDOW_SEC
        self._displayed_words = [
            w for w in self._displayed_words 
            if w.endTime > cutoff_time
        ]
        
        # Phrasal verb detection removed - will implement API-based approach later
        # (checking dictionary on hover, not hardcoding phrases)
        
        return filtered_new, revisions

    # ── helpers ──────────────────────────────────────────────────────
    def _find_overlapping_word(self, word: Word) -> Optional[Word]:
        """
        Find a displayed word that overlaps temporally with this word.
        
        Returns the provisional word if found, None otherwise.
        """
        for displayed in self._displayed_words:
            # Check temporal overlap
            overlap_start = max(word.startTime, displayed.startTime)
            overlap_end = min(word.endTime, displayed.endTime)
            overlap_duration = max(0, overlap_end - overlap_start)
            
            # Calculate overlap ratio
            word_duration = word.endTime - word.startTime
            displayed_duration = displayed.endTime - displayed.startTime
            
            if word_duration <= 0 or displayed_duration <= 0:
                continue
            
            overlap_ratio = overlap_duration / min(word_duration, displayed_duration)
            
            # If significant overlap (>50%), consider it the same word position
            if overlap_ratio >= self.MIN_OVERLAP_RATIO:
                return displayed
        
        return None
    
    def _is_already_displayed(self, word: Word) -> bool:
        """Check if word is already in displayed list."""
        key = _strip_punct(word.text)

        for displayed in self._displayed_words:
            # Check if same text at similar time
            if _strip_punct(displayed.text) == key:
                time_diff = abs(word.startTime - displayed.startTime)
                if time_diff < 0.25:  # REDUCED: Within 250ms (was 500ms)
                    return True

        return False
    
    def _replace_displayed_word(self, old: Word, new: Word):
        """Replace old word with new word in displayed list."""
        try:
            idx = self._displayed_words.index(old)
            self._displayed_words[idx] = new
        except ValueError:
            # Old word not in list (shouldn't happen, but handle gracefully)
            pass
    
    def _is_better_confidence(self, new_word: Word, old_word: Word) -> bool:
        """Check if new word has better confidence than old."""
        # Compare avg_logprob
        new_alp = new_word.avg_logprob if new_word.avg_logprob is not None else -999
        old_alp = old_word.avg_logprob if old_word.avg_logprob is not None else -999
        
        if new_alp > old_alp + 0.1:  # Significantly better
            return True
        
        # Compare word confidence
        new_conf = new_word.confidence if new_word.confidence is not None else 0
        old_conf = old_word.confidence if old_word.confidence is not None else 0
        
        if new_conf > old_conf + 0.1:
            return True
        
        return False
    
    def _seen_recently(self, key: str, word_start: float) -> bool:
        """Check if word was seen recently in displayed words."""
        for displayed in self._displayed_words:
            if _strip_punct(displayed.text) == key:
                # Check if word is at similar time position (not just same text)
                time_diff = abs(word_start - displayed.startTime)
                if time_diff < 0.4:  # Same word at ~same position
                    return True
        return False

    def _strip_ngram_prefix(self, words: list[Word]) -> list[Word]:
        """Remove stale prefix that matches tail."""
        if not self._tail or not words:
            return words

        n = min(self.NGRAM_N, len(self._tail), len(words))
        tail_slice  = self._tail[-n:]
        words_slice = [_strip_punct(w.text) for w in words[:n]]

        if tail_slice == words_slice:
            return words[n:]
        return words