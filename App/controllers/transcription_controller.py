# controllers/transcription_controller.py
"""Owns the Whisper/VAD/audio-recorder lifecycle and live transcription sessions."""

import time
import threading

from utils.app_logger import get_logger

logger = get_logger(__name__)


class TranscriptionController:
    """Loads/unloads the transcription engine and runs live capture + transcription."""

    def __init__(self):
        self.config = None
        self.whisper = None
        self.vad = None
        self.live_recorder = None
        self.streaming_transcriber = None
        self.vad_transcriber = None
        self._active_transcriber = None
        self.is_recording = False
        self._shutdown_requested = False
        self._transcription_loaded = False
        self._translate = False

    # ==================================================================
    # Lifecycle (load / unload)
    # ==================================================================

    def load(self, config):
        """Load Whisper model + audio services.  Heavy — call from UI thread with loading indicator."""
        from services.whisper_service import WhisperService
        from services.vad_service import VadService
        from services.audio_capture_live import AudioCaptureLive
        from services.live_transcriber import LiveTranscriber
        from services.vad_transcriber import VadTranscriber

        self.config = config
        self.whisper = WhisperService(config.model_size, config.use_gpu)
        self.vad = VadService()
        self.live_recorder = AudioCaptureLive(device=config.device_id)

        self.streaming_transcriber = LiveTranscriber(
            self.whisper, self.live_recorder, self.vad, config.language
        )
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
        self.streaming_transcriber = None
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
        if self.streaming_transcriber:
            self.streaming_transcriber.task = task
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

    def start_background(self, on_words_callback=None, mode="fast"):
        """Live transcription with three modes: 'fast', 'vad', 'accurate'."""
        if self.is_recording:
            return

        if mode == "vad":
            self._active_transcriber = self.vad_transcriber
            tick_interval = 0.05
            window_sec = None
        elif mode == "fast":
            self._active_transcriber = self.streaming_transcriber
            tick_interval = 0.3
            window_sec = 2.0
        else:  # accurate
            self._active_transcriber = self.streaming_transcriber
            tick_interval = 0.7
            window_sec = 3.5

        self._start_recorder("live.wav")

        def transcription_loop():
            while self.is_recording and not self._shutdown_requested:
                try:
                    if mode == "vad":
                        new_words, _ = self._active_transcriber.tick()
                    else:
                        new_words, _ = self._active_transcriber.tick(window_sec=window_sec)

                    if new_words and on_words_callback:
                        on_words_callback(new_words)
                except Exception:
                    if not self._shutdown_requested:
                        logger.exception("Transcription error")
                time.sleep(tick_interval)

        self._audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
        self._trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        self._audio_thread.start()
        self._trans_thread.start()

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
            logger.info("Stop complete")
            return result
        except Exception:
            logger.exception("Error during cleanup")
            return None
