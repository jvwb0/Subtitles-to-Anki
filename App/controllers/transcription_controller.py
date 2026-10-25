# controllers/transcription_controller.py
"""Owns the Whisper/VAD/audio-recorder lifecycle and live transcription sessions."""

import time
import threading

from services.recording_store import RecordingStore
from utils.app_logger import get_logger

logger = get_logger(__name__)


class TranscriptionController:
    """Loads/unloads the transcription engine and runs live capture + transcription."""

    def __init__(self):
        self.config = None
        self.whisper = None
        self.vad = None
        self.live_recorder = None
        self.vad_transcriber = None
        self._active_transcriber = None
        self.is_recording = False
        self._shutdown_requested = False
        self._transcription_loaded = False
        self._translate = False
        self._recordings = RecordingStore()
        self._session_lines: list[str] = []
    # ==================================================================

    def load(self, config):
        """Load Whisper model + audio services.  Heavy — call from UI thread with loading indicator."""
        from services.whisper_service import WhisperService
        from services.vad_service import VadService
        from services.audio_capture_live import AudioCaptureLive
        from services.vad_transcriber import VadTranscriber

        self.config = config
        self.whisper = WhisperService(config.model_size, config.use_gpu)
        self.vad = VadService()
        self.live_recorder = AudioCaptureLive(device=config.device_id)

        self.vad_transcriber = VadTranscriber(
            self.whisper, self.live_recorder, self.vad, config.language
        )

        self._active_transcriber = None
        self.is_recording = False
        self._shutdown_requested = False
        self._transcription_loaded = True
        self._translate = False

    def unload(self):
        """Release Whisper model + audio resources."""
        self.config = None
        self.whisper = None
        self.vad = None
        self.live_recorder = None
        self.vad_transcriber = None
        self._active_transcriber = None
        self.is_recording = False
        self._shutdown_requested = False
        self._transcription_loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._transcription_loaded

    # ==================================================================
    # Runtime toggles
    # ==================================================================

    def set_translate(self, enabled: bool):
        """Toggle Whisper translate mode (any language → English) at runtime."""
        self._translate = enabled
        task = "translate" if enabled else "transcribe"
        if self.vad_transcriber:
            self.vad_transcriber.task = task

    # ==================================================================
    # Recorder helpers
    # ==================================================================

    def _start_recorder(self, filename="live.wav"):
        self.live_recorder.start(filename)
        if self._active_transcriber:
            self._active_transcriber.reset()
        self.is_recording = True
        self._shutdown_requested = False

    def _audio_capture_loop(self):
        """Audio capture thread — checks shutdown flag on every iteration."""
        while self.is_recording and not self._shutdown_requested:
            try:
                self.live_recorder.read_chunk()
            except Exception:
                if not self._shutdown_requested:
                    logger.exception("Audio capture error")
                break
            time.sleep(0.001)

    # ==================================================================
    # Background sessions (non-blocking)
    # ==================================================================

    TICK_INTERVAL_SEC = 0.05

    def start_background(self, on_words_callback=None, on_partial_callback=None):
        """Live transcription: speech-gated, with live partial text while a sentence is spoken.

        on_words_callback(words)    final words.
        on_partial_callback(words)  live text of the open segment;
                                    an empty list means the partial text was superseded.
        """
        if self.is_recording:
            return

        self._active_transcriber = self.vad_transcriber
        wav_path = self._recordings.new_session_path(self.config)
        self._session_lines = [f"# {self.config}"]
        self._start_recorder(wav_path)

        def transcription_loop():
            while self.is_recording and not self._shutdown_requested:
                try:
                    new_words, partial = self._active_transcriber.tick()
                    if partial is not None and on_partial_callback:
                        on_partial_callback(partial)
                    if new_words:
                        self._log_final_words(new_words)
                        if on_words_callback:
                            on_words_callback(new_words)
                except Exception:
                    if not self._shutdown_requested:
                        logger.exception("Transcription error")
                time.sleep(self.TICK_INTERVAL_SEC)

        self._audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
        self._trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        self._audio_thread.start()
        self._trans_thread.start()

    def _log_final_words(self, words):
        text = " ".join(w.text for w in words)
        self._session_lines.append(f"[{words[0].startTime:7.2f} - {words[-1].endTime:7.2f}] {text}")

    def _save_session_transcript(self, wav_path):
        """Write the final transcript next to the WAV (times are session seconds, not WAV seconds)."""
        recorder = self.live_recorder
        buffered_sec = len(recorder.frames) * recorder.chunk / recorder.rate
        wav_starts_at = max(0.0, recorder.elapsed_sec - buffered_sec)
        header, *lines = self._session_lines
        self._recordings.write_transcript(
            wav_path, [header, f"# wav starts at session time {wav_starts_at:.2f}s", *lines]
        )

    def stop_background(self, save_wav=True):
        """Stop background transcription with robust cleanup."""
        if not self.is_recording:
            return None

        logger.info("Stopping transcription...")

        self._shutdown_requested = True
        self.is_recording = False

        if self.live_recorder and self.live_recorder.stream:
            try:
                self.live_recorder.stream.stop_stream()
                logger.info("Audio stream stopped")
            except Exception:
                logger.exception("Error stopping stream")

        if hasattr(self, "_trans_thread") and self._trans_thread.is_alive():
            self._trans_thread.join(timeout=10.0)
            if self._trans_thread.is_alive():
                logger.warning("Transcription thread did not finish in 10s")
            else:
                logger.info("Transcription thread stopped")

        if hasattr(self, "_audio_thread") and self._audio_thread.is_alive():
            self._audio_thread.join(timeout=2.0)
            if self._audio_thread.is_alive():
                logger.warning("Audio thread did not finish in 2s")
            else:
                logger.info("Audio thread stopped")

        try:
            result = self.live_recorder.cleanup_and_save(save_wav=save_wav)
            if result:
                logger.info("WAV saved: %s", result)
                self._save_session_transcript(result)
            logger.info("Stop complete")
            return result
        except Exception:
            logger.exception("Error during cleanup")
            return None
