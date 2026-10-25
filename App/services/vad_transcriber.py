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
from collections import Counter
from models.word import Word, shift_timestamps
from services.audio_conversion import AudioConverter
from services.partial_stabilizer import PartialStabilizer
from services.segment_splitter import SegmentSplitter
from utils.text_utils import strip_punct as _strip_punct


class VadTranscriber:
    # VAD state machine settings
    SPEECH_THRESHOLD = 0.5       # Silero prob >= this = speech
    PAUSE_FRAMES     = 10        # 10 × 32ms = 320ms silence = segment end
    LONG_SEGMENT_SEC = 4.0       # after this much speech, a shorter pause already ends it
    PAUSE_FRAMES_LONG = 5        # 5 × 32ms = 160ms
    MIN_SEGMENT_SEC  = 0.15      # Ignore segments shorter than this
    MAX_SPEECH_SEC   = 8.0       # Safety cut only: speech that never pauses is split at its best boundary

    # Audio windowing
    CONTEXT_SEC      = 0.5       # Context before segment for Whisper
    OVERLAP_SEC      = 0.8       # Tail kept for next segment when no boundary was found
    FLUSH_CUTOFF_SEC = 0.4       # Hold back last N seconds on a safety cut

    # Live partial text while speech is ongoing
    PARTIAL_INTERVAL_SEC = 0.6   # re-transcribe the open segment this often
    MIN_PARTIAL_SPEECH_SEC = 0.5 # don't guess before this much speech

    # Text of recent finals handed to Whisper to keep punctuation/casing consistent
    CONTEXT_PROMPT_CHARS = 150

    # Dedup
    TIME_GRACE_SEC   = 0.15

    def __init__(self, whisper, recorder, vad, language: str = "en",
                 task: str = "transcribe", stabilize_partials: bool = True,
                 use_context_prompt: bool = True):
        self.stabilize_partials = stabilize_partials
        self.use_context_prompt = use_context_prompt
        self._stabilizer = PartialStabilizer()
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
        self._context_text     = ""
        self.cut_counts        = Counter()  # why segments ended: pause / forced_split / forced_fallback
        self._stabilizer.reset()

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
        seg_dur = self._last_speech_vad - self._speech_start_vad
        pause_frames = self.PAUSE_FRAMES_LONG if seg_dur >= self.LONG_SEGMENT_SEC else self.PAUSE_FRAMES
        if pause >= pause_frames * frame_sec:
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

        prompt = self._context_text if self.use_context_prompt else None
        words = self.whisper.transcribe(audio, self.language, task=self.task, prompt=prompt)
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
        words = self._unseen(self._transcribe_window(grab_sec))
        return self._stabilizer.update(words) if self.stabilize_partials else words

    def _do_transcribe(self, forced: bool):
        window_sec = self.CONTEXT_SEC + (self._vad_clock - self._speech_start_vad) + 0.2
        words = self._transcribe_window(window_sec + self._backlog_sec())
        self._last_partial_vad = self._vad_clock

        new_words = self._unseen(words)
        if forced:
            new_words = self._finalize_up_to_best_boundary(new_words)
        else:
            self.cut_counts["pause"] += 1

        self._stabilizer.reset()
        if new_words:
            self._last_emitted_end = new_words[-1].endTime
            self._remember_context(new_words)

        return new_words

    def _finalize_up_to_best_boundary(self, words: list) -> list:
        """Speech never paused: finalize up to the most natural cut and keep the rest open."""
        stable_end = self.recorder.elapsed_sec - self.FLUSH_CUTOFF_SEC
        count = SegmentSplitter.split_index(words, stable_end)

        if count is None:
            self.cut_counts["forced_fallback"] += 1
            self._speech_start_vad = self._vad_clock - self.OVERLAP_SEC
            return [w for w in words if w.endTime <= stable_end]

        self.cut_counts["forced_split"] += 1
        final, rest = words[:count], words[count:]
        resume = rest[0].startTime - 0.1 if rest else final[-1].endTime
        self._speech_start_vad = min(max(resume, self._speech_start_vad), self._vad_clock - 0.5)
        return final

    def _remember_context(self, words: list):
        text = f"{self._context_text} {' '.join(w.text for w in words)}".strip()
        self._context_text = text[-self.CONTEXT_PROMPT_CHARS:]
