# controllers/app_controller.py
import time
import threading
from models.config import TranscriptionConfig
from services.whisper_service import WhisperService
from services.audio_capture_live import AudioCaptureLive
from services.audio_capture_fixed import AudioCaptureFixed
from services.live_transcriber import LiveTranscriber
from utils.audio_utils import prepareAudioFromWav


class AppController:
    def __init__(self, config):
        self.config = config
        self.whisper = WhisperService(config.model_size, config.use_gpu)
        self.fixed_recorder = AudioCaptureFixed(device=config.device_id)
        self.live_recorder  = AudioCaptureLive(device=config.device_id)
        self.live_transcriber = LiveTranscriber(
            self.whisper.model, self.live_recorder, config.language
        )
        self.is_recording = False

    # ── wav ──────────────────────────────────────────────────────────
    def transcribe_wav(self, filename):
        audio = prepareAudioFromWav(filename)
        return self.whisper.transcribe(audio, self.config.language)

    # ── recorder helpers ─────────────────────────────────────────────
    def start_live(self, filename="live.wav"):
        self.live_recorder.start(filename)
        self.live_transcriber.reset()
        self.is_recording = True

    def stop_live(self, save_wav=True):
        self.is_recording = False
        return self.live_recorder.stop(saveWav=save_wav)

    def live_tick(self):
        if self.is_recording:
            self.live_recorder.readChunk()

    # ── shared audio-capture thread (used by every background mode) ─
    def _audio_capture_loop(self):
        while self.is_recording:
            self.live_tick()
            time.sleep(0.001)

    # ==================================================================
    # CLI (blocking) sessions — unchanged interface
    # ==================================================================
    def run_live_session(self, duration_sec=10.0, window_sec=2.0, tick_sleep=0.5,
                         filename="live.wav", save_wav=True, on_words_callback=None):
        self.start_live(filename)
        start_time = time.time()

        def transcription_loop():
            while self.is_recording:
                try:
                    new_words = self.live_transcriber.tick(window_sec)
                    if new_words and on_words_callback:
                        on_words_callback(new_words)
                except Exception as e:
                    print(f"❌ Transcription error: {e}")
                time.sleep(tick_sleep)

        audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
        trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        audio_thread.start()
        trans_thread.start()

        try:
            while time.time() - start_time < duration_sec:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass

        self.is_recording = False
        trans_thread.join(timeout=2.0)
        audio_thread.join(timeout=2.0)
        print(f"\n📊 Recorded {len(self.live_recorder.frames)} chunks in "
              f"{time.time()-start_time:.1f}s")
        self.stop_live(save_wav=save_wav)

    def run_manual_session_chunked(self, chunk_duration=3.0, filename="live.wav",
                                    save_wav=True, on_words_callback=None):
        """CLI blocking chunked mode."""
        self.start_live(filename)
        last_transcription_time = time.time()

        def transcription_loop():
            nonlocal last_transcription_time
            last_chunk_idx = 0
            while self.is_recording:
                if time.time() - last_transcription_time >= chunk_duration:
                    try:
                        total = len(self.live_recorder.frames)
                        if total > last_chunk_idx:
                            new_chunks = self.live_recorder.frames[last_chunk_idx:total]
                            from services.audio_conversion import AudioConverter
                            audio = AudioConverter.chunks_to_float_mono_16k(
                                new_chunks, self.live_recorder.rate, self.live_recorder.channels)
                            if audio.size > 0:
                                words = self.whisper.transcribe(audio, self.config.language)
                                if words and on_words_callback:
                                    on_words_callback(words)
                            last_chunk_idx = total
                        last_transcription_time = time.time()
                    except Exception as e:
                        print(f"❌ Transcription error: {e}")
                time.sleep(0.1)

        audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
        trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        audio_thread.start()
        trans_thread.start()

        try:
            input()
        except KeyboardInterrupt:
            pass

        self.is_recording = False
        trans_thread.join(timeout=2.0)
        audio_thread.join(timeout=2.0)
        print(f"\n📊 Recorded {len(self.live_recorder.frames)} chunks")
        self.stop_live(save_wav=save_wav)

    # ==================================================================
    # GUI background sessions (non-blocking)
    # ==================================================================

    # ── Live (rolling window) ────────────────────────────────────────
    def start_live_background(self, window_sec=2.0, tick_sleep=0.5,
                              on_words_callback=None):
        """
        Rolling-window live transcription.
        Tuned defaults: 2 s window, 0.5 s tick.
          - 2 s window  = less overlap than 3 s, so dedup has less work
          - 0.5 s tick  = whisper runs twice/sec, plenty for live feel,
                          and halves CPU vs the old 0.2 s tick
        """
        if self.is_recording:
            return
        self.start_live("live.wav")

        def transcription_loop():
            while self.is_recording:
                try:
                    new_words = self.live_transcriber.tick(window_sec)
                    if new_words and on_words_callback:
                        on_words_callback(new_words)
                except Exception as e:
                    print(f"❌ Transcription error: {e}")
                time.sleep(tick_sleep)

        self._audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
        self._trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        self._audio_thread.start()
        self._trans_thread.start()

    # ── Chunked (non-overlapping, 3 s) ───────────────────────────────
    def start_chunked_background(self, chunk_duration=3.0, on_words_callback=None):
        """
        Non-overlapping chunks.  Most accurate but highest latency (3 s).
        """
        if self.is_recording:
            return
        self.start_live("live.wav")

        def transcription_loop():
            last_chunk_idx = 0
            last_t         = time.time()
            while self.is_recording:
                if time.time() - last_t >= chunk_duration:
                    try:
                        total = len(self.live_recorder.frames)
                        if total > last_chunk_idx:
                            new_chunks = self.live_recorder.frames[last_chunk_idx:total]
                            from services.audio_conversion import AudioConverter
                            audio = AudioConverter.chunks_to_float_mono_16k(
                                new_chunks, self.live_recorder.rate, self.live_recorder.channels)
                            if audio.size > 0:
                                words = self.whisper.transcribe(audio, self.config.language)
                                if words and on_words_callback:
                                    on_words_callback(words)
                            last_chunk_idx = total
                        last_t = time.time()
                    except Exception as e:
                        print(f"❌ Transcription error: {e}")
                time.sleep(0.1)

        self._audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
        self._trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        self._audio_thread.start()
        self._trans_thread.start()

    # ── Overlapping chunked ("best of both") ────────────────────────
    def start_overlapping_chunked_background(self, chunk_duration=3.0,
                                              step_duration=1.5,
                                              on_words_callback=None):
        """
        Chunked accuracy at ~half the latency.

        How it works:
          - Every `step_duration` seconds (default 1.5 s) we grab the last
            `chunk_duration` seconds (default 3.0 s) of audio and transcribe it.
          - Because we always transcribe a full 3 s window, whisper has the
            same context as the pure-chunked mode → same accuracy.
          - Because we do it every 1.5 s instead of every 3 s, new words
            appear twice as fast → half the perceived latency.
          - Dedup is handled by LiveTranscriber.tick() — we feed it the same
            rolling window it already knows how to dedup, so no extra logic
            needed here.

        step_duration should be <= chunk_duration.  1.5 / 3.0 is the sweet
        spot: good latency without running whisper too often.
        """
        if self.is_recording:
            return
        self.start_live("live.wav")

        def transcription_loop():
            last_t = time.time()
            while self.is_recording:
                if time.time() - last_t >= step_duration:
                    try:
                        # reuse LiveTranscriber — it grabs the last
                        # chunk_duration seconds internally and dedups
                        new_words = self.live_transcriber.tick(chunk_duration)
                        if new_words and on_words_callback:
                            on_words_callback(new_words)
                        last_t = time.time()
                    except Exception as e:
                        print(f"❌ Transcription error: {e}")
                time.sleep(0.1)

        self._audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
        self._trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        self._audio_thread.start()
        self._trans_thread.start()

    # ── shared stop ──────────────────────────────────────────────────
    def stop_live_background(self, save_wav=True):
        if not self.is_recording:
            return None
        self.is_recording = False
        if hasattr(self, "_trans_thread"):
            self._trans_thread.join(timeout=2.0)
        if hasattr(self, "_audio_thread"):
            self._audio_thread.join(timeout=2.0)
        return self.stop_live(save_wav=save_wav)