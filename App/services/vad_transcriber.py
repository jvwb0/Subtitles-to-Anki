# services/vad_transcriber.py
"""
VAD-gated transcription — waits for natural pauses before transcribing.

Benefits:
- Whisper sees complete speech segments with natural boundaries
- Higher accuracy (no mid-sentence cuts)
- Lower CPU (Whisper only called on pause events)

While the speaker is still talking, a *partial* hypothesis of the current
segment is produced every PARTIAL_INTERVAL_SEC so captions follow the speech
closely. The final transcription at the pause replaces the partial text.
"""

import numpy as np
from models.word import Word, shift_timestamps
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

    # Live partial text while speech is ongoing
    PARTIAL_INTERVAL_SEC = 0.6   # re-transcribe the open segment this often
    MIN_PARTIAL_SPEECH_SEC = 0.5 # don't guess before this much speech

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
        self._last_partial_vad = 0.0

        self._last_emitted_end = 0.0

    def tick(self):
        """
        Call every ~50ms. Returns (final_words, partial_words):
          - segment finished -> (final_words, [])      partial text is superseded
          - speech ongoing   -> ([], partial_words)    refreshed every PARTIAL_INTERVAL_SEC
          - nothing to report -> ([], None)            partial_words None = "no change"
        """
        event = self._run_vad()
        if event == "segment_end":
            return self._do_transcribe(forced=False), []
        if event == "max_speech":
            return self._do_transcribe(forced=True), []
        if self._partial_due():
            return [], self._transcribe_partial()
        return [], None

    def _partial_due(self) -> bool:
        if not self._in_speech:
            return False
        if self._last_speech_vad - self._speech_start_vad < self.MIN_PARTIAL_SPEECH_SEC:
            return False
        return self._vad_clock - self._last_partial_vad >= self.PARTIAL_INTERVAL_SEC

    def _run_vad(self):
        new_chunks, self._chunk_cursor = self.recorder.chunks_since(self._chunk_cursor)
        if not new_chunks:
            return None

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

    def _transcribe_window(self, grab_sec: float) -> list:
        """Transcribe the last `grab_sec` of audio; words carry absolute timestamps."""
        abs_now = self.recorder.elapsed_sec
        grab_sec = min(grab_sec, abs_now, self.recorder.MAX_BUFFER_SECONDS)
        if grab_sec <= 0:
            return []

        chunks = self.recorder.get_recent_chunks(grab_sec)
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
        shift_timestamps(words, max(0.0, abs_now - grab_sec))
        return words

    def _backlog_sec(self) -> float:
        """Audio captured but not yet consumed by VAD (inference blocks the tick loop)."""
        return max(0.0, self.recorder.elapsed_sec - self._vad_clock)

    def _unseen(self, words: list) -> list:
        """Words not already emitted as final text."""
        return [
            w for w in words
            if _strip_punct(w.text) and w.endTime > self._last_emitted_end + self.TIME_GRACE_SEC
        ]

    def _transcribe_partial(self) -> list:
        self._last_partial_vad = self._vad_clock
        speech_dur = self._last_speech_vad - self._speech_start_vad
        grab_sec = self.CONTEXT_SEC + speech_dur + 0.2 + self._backlog_sec()
        return self._unseen(self._transcribe_window(grab_sec))

    def _do_transcribe(self, forced: bool):
        abs_now = self.recorder.elapsed_sec
        backlog = self._backlog_sec()

        if forced:
            grab_sec = self.MAX_SPEECH_SEC + self.CONTEXT_SEC + 0.2 + backlog
        else:
            speech_dur = self._last_speech_vad - self._speech_start_vad
            silence_dur = self._vad_clock - self._last_speech_vad
            grab_sec = self.CONTEXT_SEC + speech_dur + silence_dur + 0.2 + backlog

        words = self._transcribe_window(grab_sec)
        self._last_partial_vad = self._vad_clock

        # Forced flush: hold back unstable tail
        if forced:
            safe_abs = abs_now - self.FLUSH_CUTOFF_SEC
            words = [w for w in words if w.endTime <= safe_abs]
            self._speech_start_vad = self._vad_clock - self.OVERLAP_SEC

        new_words = self._unseen(words)
        if new_words:
            self._last_emitted_end = new_words[-1].endTime

        return new_words
