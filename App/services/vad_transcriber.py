# services/vad_transcriber.py
"""
VAD-gated transcription — waits for natural pauses before transcribing.

Benefits:
- Whisper sees complete speech segments with natural boundaries
- Higher accuracy (no mid-sentence cuts)
- Lower CPU (Whisper only called on pause events)
"""

import numpy as np
from models.word import Word
from services.audio_conversion import AudioConverter
from utils.text_utils import strip_punct as _strip_punct


class VadTranscriber:
    # VAD state machine settings
    SPEECH_THRESHOLD = 0.5       # Silero prob >= this = speech
    PAUSE_FRAMES     = 10        # 10 × 32ms = 320ms silence = segment end
    MIN_SEGMENT_SEC  = 0.15      # Ignore segments shorter than this
    MAX_SPEECH_SEC   = 4.0       # Force flush after 4s continuous speech

    # Audio windowing
    CONTEXT_SEC      = 0.5       # Context before segment for Whisper
    OVERLAP_SEC      = 0.8       # Tail kept for next segment on forced flush
    FLUSH_CUTOFF_SEC = 0.4       # Hold back last N seconds on forced flush

    # Dedup
    TIME_GRACE_SEC   = 0.15

    def __init__(self, whisper, recorder, vad, language: str = "en",
                 task: str = "transcribe"):
        self.whisper  = whisper
        self.recorder = recorder
        self.vad      = vad
        self.language = language
        self.task     = task
        self.reset()

    def reset(self):
        self.vad.reset()

        self._in_speech        = False
        self._speech_start_vad = 0.0
        self._last_speech_vad  = 0.0
        self._vad_clock        = 0.0
        self._vad_buf          = np.array([], dtype=np.float32)
        self._chunk_cursor     = 0

        self._last_emitted_end = 0.0

    def tick(self):
        """
        Call every ~50ms. Returns (new_words, []) on speech boundary, else ([], []).
        Returns tuple for API compatibility with streaming transcriber.
        """
        event = self._run_vad()
        if event == "segment_end":
            return self._do_transcribe(forced=False), []
        if event == "max_speech":
            return self._do_transcribe(forced=True), []
        return [], []

    def _run_vad(self):
        n = len(self.recorder.frames)
        if n < self._chunk_cursor:
            self._chunk_cursor = n
        if n <= self._chunk_cursor:
            return None

        new_chunks = self.recorder.frames[self._chunk_cursor:n]
        self._chunk_cursor = n

        audio = AudioConverter.chunks_to_float_mono_16k(
            new_chunks,
            srcRate=self.recorder.rate,
            channels=self.recorder.channels,
        )
        if audio.size == 0:
            return None

        self._vad_buf = np.append(self._vad_buf, audio)

        event = None
        frame_sec = self.vad.FRAME_SIZE / self.vad.SAMPLE_RATE  # 0.032

        while len(self._vad_buf) >= self.vad.FRAME_SIZE and event is None:
            frame = self._vad_buf[:self.vad.FRAME_SIZE]
            self._vad_buf = self._vad_buf[self.vad.FRAME_SIZE:]
            prob = self.vad.speech_prob(frame)
            event = self._state_step(prob, frame_sec)
            self._vad_clock += frame_sec

        return event

    def _state_step(self, prob: float, frame_sec: float):
        t_after = self._vad_clock + frame_sec

        if prob >= self.SPEECH_THRESHOLD:
            if not self._in_speech:
                self._speech_start_vad = self._vad_clock
                self._in_speech = True
            self._last_speech_vad = t_after

            if (t_after - self._speech_start_vad) >= self.MAX_SPEECH_SEC:
                return "max_speech"
            return None

        if not self._in_speech:
            return None

        pause = t_after - self._last_speech_vad
        if pause >= self.PAUSE_FRAMES * frame_sec:
            seg_dur = self._last_speech_vad - self._speech_start_vad
            self._in_speech = False
            if seg_dur < self.MIN_SEGMENT_SEC:
                return None
            return "segment_end"

        return None

    def _abs_now(self):
        return (len(self.recorder.frames) * self.recorder.chunk) / self.recorder.rate

    def _do_transcribe(self, forced: bool):
        abs_now = self._abs_now()

        if forced:
            grab_sec = self.MAX_SPEECH_SEC + self.CONTEXT_SEC + 0.2
        else:
            speech_dur = self._last_speech_vad - self._speech_start_vad
            silence_dur = self._vad_clock - self._last_speech_vad
            grab_sec = self.CONTEXT_SEC + speech_dur + silence_dur + 0.2

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

        words = self.whisper.transcribe(audio, self.language, task=self.task)
        if not words:
            return []

        # Map to absolute timestamps
        audio_start = max(0.0, abs_now - grab_sec)
        for w in words:
            w.startTime += audio_start
            w.endTime += audio_start

        # Forced flush: hold back unstable tail
        if forced:
            safe_abs = abs_now - self.FLUSH_CUTOFF_SEC
            words = [w for w in words if w.endTime <= safe_abs]
            self._speech_start_vad = self._vad_clock - self.OVERLAP_SEC

        # Dedup
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
