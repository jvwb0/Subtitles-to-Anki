"""
VAD-gated live transcription — YouTube-CC style.

Instead of blindly re-transcribing a sliding window every tick, we use
Silero VAD to detect speech/silence transitions in real-time:

  tick() runs every ~50 ms  (VAD processing: < 1 ms per frame)
       │
       ├─ New audio →  16 kHz mono  →  VAD frames (512 samples, 32 ms)
       │
       ├─ State machine
       │      SILENCE ──(speech detected)──→  SPEECH
       │      SPEECH  ──(≥320 ms silence)──→  segment_end   → transcribe
       │      SPEECH  ──(≥4 s continuous)──→  max_speech    → forced flush
       │
       └─ Transcription triggered only on boundary events
              • segment_end : segment is complete → Whisper sees clean boundary
                              → high accuracy, emit all words
              • max_speech  : segment ongoing    → hold back the last 400 ms
                              (may still change) → emit only the stable prefix

Dedup is minimal: segments don't overlap except for the forced-flush tail,
which is handled by a single absolute-timestamp cutoff.
"""

import re
import numpy as np
from models.word import Word
from services.audio_conversion import AudioConverter


def _strip_punct(text: str) -> str:
    return re.sub(r'[^\w\s]', '', text.lower()).strip()


class LiveTranscriber:
    # ── VAD state-machine ────────────────────────────────────────
    SPEECH_THRESHOLD = 0.5       # Silero prob ≥ this → speech
    PAUSE_FRAMES     = 10        # × 32 ms = 320 ms silence → segment end
    MIN_SEGMENT_SEC  = 0.15      # ignore segments shorter than this (clicks/noise)
    MAX_SPEECH_SEC   = 4.0       # forced flush after this many seconds of speech

    # ── audio windowing ──────────────────────────────────────────
    CONTEXT_SEC      = 0.5       # prepended before each segment for Whisper context
    OVERLAP_SEC      = 0.8       # forced-flush tail kept as next segment's context
    FLUSH_CUTOFF_SEC = 0.4       # last N seconds of forced flush are "unstable" → held back

    # ── dedup ────────────────────────────────────────────────────
    TIME_GRACE_SEC   = 0.15      # skip words ending ≤ lastEmitted + this

    def __init__(self, whisper, recorder, vad, language: str = "en"):
        self.whisper  = whisper
        self.recorder = recorder
        self.vad      = vad
        self.language = language
        self.reset()

    # ── lifecycle ────────────────────────────────────────────────
    def reset(self):
        self.vad.reset()                          # LSTM state

        self._in_speech        = False
        self._speech_start_vad = 0.0              # VAD-clock seconds
        self._last_speech_vad  = 0.0
        self._vad_clock        = 0.0              # total seconds processed by VAD
        self._vad_buf          = np.array([], dtype=np.float32)
        self._chunk_cursor     = 0                # last recorder-frame index consumed

        self._last_emitted_end = 0.0              # absolute time of last word we emitted

    # ── public tick ──────────────────────────────────────────────
    def tick(self) -> list[Word]:
        """
        Call every ~50 ms.  Usually returns [].  On a speech boundary
        it transcribes and returns new words.
        """
        event = self._run_vad()
        if event == "segment_end":
            return self._do_transcribe(forced=False)
        if event == "max_speech":
            return self._do_transcribe(forced=True)
        return []

    # ── VAD processing ───────────────────────────────────────────
    def _run_vad(self) -> str | None:
        n = len(self.recorder.frames)
        if n < self._chunk_cursor:          # buffer was trimmed
            self._chunk_cursor = n
        if n <= self._chunk_cursor:
            return None

        new_chunks        = self.recorder.frames[self._chunk_cursor:n]
        self._chunk_cursor = n

        audio = AudioConverter.chunks_to_float_mono_16k(
            new_chunks,
            srcRate=self.recorder.rate,
            channels=self.recorder.channels,
        )
        if audio.size == 0:
            return None

        self._vad_buf = np.append(self._vad_buf, audio)

        event     = None
        frame_sec = self.vad.FRAME_SIZE / self.vad.SAMPLE_RATE   # 0.032

        while len(self._vad_buf) >= self.vad.FRAME_SIZE and event is None:
            frame            = self._vad_buf[:self.vad.FRAME_SIZE]
            self._vad_buf    = self._vad_buf[self.vad.FRAME_SIZE:]
            prob             = self.vad.speech_prob(frame)
            event            = self._state_step(prob, frame_sec)
            self._vad_clock += frame_sec

        return event

    def _state_step(self, prob: float, frame_sec: float) -> str | None:
        """One frame through the speech state machine."""
        t_after = self._vad_clock + frame_sec   # clock AFTER this frame

        if prob >= self.SPEECH_THRESHOLD:
            if not self._in_speech:
                self._speech_start_vad = self._vad_clock
                self._in_speech        = True
            self._last_speech_vad = t_after

            if (t_after - self._speech_start_vad) >= self.MAX_SPEECH_SEC:
                return "max_speech"
            return None

        # — silence frame —
        if not self._in_speech:
            return None

        pause = t_after - self._last_speech_vad
        if pause >= self.PAUSE_FRAMES * frame_sec:
            seg_dur = self._last_speech_vad - self._speech_start_vad
            self._in_speech = False
            if seg_dur < self.MIN_SEGMENT_SEC:
                return None           # too short, ignore
            return "segment_end"

        return None

    # ── transcription ────────────────────────────────────────────
    def _abs_now(self) -> float:
        return (len(self.recorder.frames) * self.recorder.chunk) / self.recorder.rate

    def _do_transcribe(self, forced: bool) -> list[Word]:
        abs_now = self._abs_now()

        if forced:
            grab_sec = self.MAX_SPEECH_SEC + self.CONTEXT_SEC + 0.2
        else:
            speech_dur  = self._last_speech_vad  - self._speech_start_vad
            silence_dur = self._vad_clock        - self._last_speech_vad
            grab_sec    = self.CONTEXT_SEC + speech_dur + silence_dur + 0.2

        # Clamp to what's available
        grab_sec = min(grab_sec, abs_now)
        if grab_sec <= 0:
            return []

        chunks = self.recorder.getRecentChunks(grab_sec)
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

        # — map word timestamps to absolute time —
        audio_start = max(0.0, abs_now - grab_sec)
        for w in words:
            w.startTime += audio_start
            w.endTime   += audio_start

        # — forced flush: hold back the unstable tail —
        if forced:
            safe_abs = abs_now - self.FLUSH_CUTOFF_SEC
            words    = [w for w in words if w.endTime <= safe_abs]
            # slide the segment window forward; next segment reuses the tail
            self._speech_start_vad = self._vad_clock - self.OVERLAP_SEC

        # — dedup & emit —
        new_words = []
        for w in words:
            if not _strip_punct(w.text):
                continue
            if w.endTime <= self._last_emitted_end + self.TIME_GRACE_SEC:
                continue
            new_words.append(w)

        if new_words:
            self._last_emitted_end = new_words[-1].endTime

        return new_words
