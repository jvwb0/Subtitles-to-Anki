# controllers/app_controller.py
import time
import threading
from services.whisper_service import WhisperService
from services.vad_service import VadService
from services.audio_capture_live import AudioCaptureLive
from services.audio_conversion import AudioConverter
from services.live_transcriber import LiveTranscriber


class AppController:
    """GUI-only controller with robust shutdown handling."""
    
    def __init__(self, config):
        self.config = config
        self.whisper        = WhisperService(config.model_size, config.use_gpu)
        self.vad            = VadService()
        self.live_recorder  = AudioCaptureLive(device=config.device_id)
        self.live_transcriber = LiveTranscriber(
            self.whisper, self.live_recorder, self.vad, config.language
        )
        self.is_recording = False
        self._shutdown_requested = False

    # ── recorder helpers ─────────────────────────────────────────────
    def start_live(self, filename="live.wav"):
        self.live_recorder.start(filename)
        self.live_transcriber.reset()
        self.is_recording = True
        self._shutdown_requested = False

    # ── shared audio-capture thread ──────────────────────────────────
    def _audio_capture_loop(self):
        """Audio capture thread — checks shutdown flag on every iteration."""
        while self.is_recording and not self._shutdown_requested:
            try:
                self.live_recorder.readChunk()
            except Exception as e:
                # Expected during shutdown when stream is stopped
                if not self._shutdown_requested:
                    print(f"⚠️  Audio capture error: {e}")
                break
            time.sleep(0.001)

    # ==================================================================
    # GUI background sessions (non-blocking)
    # ==================================================================

    def start_live_background(self, on_words_callback=None, **_kwargs):
        """
        VAD-gated live transcription — YouTube CC style.

        Uses Silero VAD to detect speech/silence transitions in real-time.
        Transcription is triggered at natural pause points (320ms silence) or
        after 4 seconds of continuous speech.

        Args:
            on_words_callback: Callback function for new words

        Result:
            - Fast response to pauses (~350ms latency: pause + inference)
            - High accuracy (Whisper sees complete speech segments)
            - Low CPU (VAD processing: <1ms per frame, Whisper only on boundaries)
        """
        if self.is_recording:
            return
        self.start_live("live.wav")

        def transcription_loop():
            while self.is_recording and not self._shutdown_requested:
                try:
                    new_words = self.live_transcriber.tick()
                    if new_words and on_words_callback:
                        on_words_callback(new_words)
                except Exception as e:
                    if not self._shutdown_requested:
                        print(f"❌ Transcription error: {e}")
                time.sleep(0.05)  # 50ms tick for VAD processing

        self._audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
        self._trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        self._audio_thread.start()
        self._trans_thread.start()

    def start_overlapping_chunked_background(self, on_words_callback=None, **_kwargs):
        """
        VAD-gated live transcription (same as start_live_background).

        Legacy method name kept for API compatibility — both modes now use
        the same VAD-based approach.
        """
        self.start_live_background(on_words_callback=on_words_callback)

    def stop_live_background(self, save_wav=True):
        """
        Stop background transcription with robust cleanup.
        
        CRITICAL: Stop audio stream FIRST to unblock the audio thread's blocking read(),
        THEN join threads. This prevents the audio thread from hanging.
        """
        if not self.is_recording:
            return None
        
        print("🛑 Stopping transcription...")
        
        # Step 1: Signal shutdown
        self._shutdown_requested = True
        self.is_recording = False
        
        # Step 2: CRITICAL - Stop the audio stream to unblock read()
        #         This must happen BEFORE joining threads
        if self.live_recorder and self.live_recorder.stream:
            try:
                self.live_recorder.stream.stop_stream()
                print("   ✓ Audio stream stopped")
            except Exception as e:
                print(f"   ⚠️  Error stopping stream: {e}")
        
        # Step 3: Wait for threads to finish (now they can exit cleanly)
        if hasattr(self, "_trans_thread") and self._trans_thread.is_alive():
            self._trans_thread.join(timeout=10.0)
            if self._trans_thread.is_alive():
                print("   ⚠️  Transcription thread did not finish in 10s")
            else:
                print("   ✓ Transcription thread stopped")
        
        if hasattr(self, "_audio_thread") and self._audio_thread.is_alive():
            self._audio_thread.join(timeout=2.0)  # should be instant now
            if self._audio_thread.is_alive():
                print("   ⚠️  Audio thread did not finish in 2s")
            else:
                print("   ✓ Audio thread stopped")
        
        # Step 4: Sync CUDA if GPU was used
        if self.config.use_gpu:
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                    print("   ✓ CUDA synchronized")
            except Exception:
                pass
        
        # Step 5: Cleanup and optionally save WAV
        try:
            result = self.live_recorder.cleanup_and_save(save_wav=save_wav)
            if result:
                print(f"   ✓ WAV saved: {result}")
            print("✅ Stop complete")
            return result
        except Exception as e:
            print(f"   ⚠️  Error during cleanup: {e}")
            return None