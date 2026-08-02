# controllers/app_controller.py
import time
import threading

from services.definition_service import (
    fetch_definition, fetch_details,
)
from services.anki_service import (
    ensure_anki_running, get_deck_names, create_deck,
    add_note, build_note_fields,
)


class AppController:
    """Central controller — always available for definition/Anki,
    transcription loaded on demand via load_transcription()."""

    def __init__(self):
        # Transcription state (populated by load_transcription)
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

        # Dual subtitle (original + English translation)
        self._dual_subtitle_enabled = False
        self._translation_service = None          # lazy init

    # ==================================================================
    # Transcription lifecycle
    # ==================================================================

    def load_transcription(self, config):
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

    def set_translate(self, enabled: bool):
        """Toggle Whisper translate mode (any language → English) at runtime."""
        self._translate = enabled
        task = "translate" if enabled else "transcribe"
        if self.streaming_transcriber:
            self.streaming_transcriber.task = task
        if self.vad_transcriber:
            self.vad_transcriber.task = task

    # ── dual subtitle (original + translation) ─────────────────────

    def set_dual_subtitle(self, enabled: bool):
        """Toggle dual-subtitle mode (show original + English translation)."""
        self._dual_subtitle_enabled = enabled
        if not enabled and self._translation_service:
            self._translation_service.clear()

    @property
    def is_dual_subtitle_enabled(self) -> bool:
        return self._dual_subtitle_enabled

    def translate_subtitle(self, text: str, source_lang: str, callback):
        """Translate subtitle text asynchronously.
        callback(translated_text) called on a BG thread."""
        if not self._dual_subtitle_enabled:
            return
        if self._translation_service is None:
            from services.translation_service import TranslationService
            self._translation_service = TranslationService()
        self._translation_service.set_source_lang(source_lang)
        self._translation_service.translate_async(text, callback)

    def unload_transcription(self):
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
    def is_transcription_loaded(self) -> bool:
        return self._transcription_loaded

    # ── recorder helpers ─────────────────────────────────────────────
    def start_live(self, filename="live.wav"):
        self.live_recorder.start(filename)
        if self._active_transcriber:
            self._active_transcriber.reset()
        self.is_recording = True
        self._shutdown_requested = False

    # ── shared audio-capture thread ──────────────────────────────────
    def _audio_capture_loop(self):
        """Audio capture thread — checks shutdown flag on every iteration."""
        while self.is_recording and not self._shutdown_requested:
            try:
                self.live_recorder.readChunk()
            except Exception as e:
                if not self._shutdown_requested:
                    print(f"⚠️  Audio capture error: {e}")
                break
            time.sleep(0.001)

    # ==================================================================
    # GUI background sessions (non-blocking)
    # ==================================================================

    def start_live_background(self, on_words_callback=None, mode="fast", **_kwargs):
        """Live transcription with three modes."""
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

        self.start_live("live.wav")

        def transcription_loop():
            while self.is_recording and not self._shutdown_requested:
                try:
                    if mode == "vad":
                        new_words, _ = self._active_transcriber.tick()
                    else:
                        new_words, _ = self._active_transcriber.tick(windowSec=window_sec)

                    if new_words and on_words_callback:
                        on_words_callback(new_words)
                except Exception as e:
                    if not self._shutdown_requested:
                        print(f"❌ Transcription error: {e}")
                time.sleep(tick_interval)

        self._audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
        self._trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        self._audio_thread.start()
        self._trans_thread.start()

    def start_overlapping_chunked_background(self, on_words_callback=None, **_kwargs):
        """Legacy method - uses accurate mode."""
        self.start_live_background(on_words_callback=on_words_callback, mode="accurate")

    def stop_live_background(self, save_wav=True):
        """Stop background transcription with robust cleanup."""
        if not self.is_recording:
            return None

        print("🛑 Stopping transcription...")

        self._shutdown_requested = True
        self.is_recording = False

        if self.live_recorder and self.live_recorder.stream:
            try:
                self.live_recorder.stream.stop_stream()
                print("   ✓ Audio stream stopped")
            except Exception as e:
                print(f"   ⚠️  Error stopping stream: {e}")

        if hasattr(self, "_trans_thread") and self._trans_thread.is_alive():
            self._trans_thread.join(timeout=10.0)
            if self._trans_thread.is_alive():
                print("   ⚠️  Transcription thread did not finish in 10s")
            else:
                print("   ✓ Transcription thread stopped")

        if hasattr(self, "_audio_thread") and self._audio_thread.is_alive():
            self._audio_thread.join(timeout=2.0)
            if self._audio_thread.is_alive():
                print("   ⚠️  Audio thread did not finish in 2s")
            else:
                print("   ✓ Audio thread stopped")

        if self.config and self.config.use_gpu:
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                    print("   ✓ CUDA synchronized")
            except Exception:
                pass

        try:
            result = self.live_recorder.cleanup_and_save(save_wav=save_wav)
            if result:
                print(f"   ✓ WAV saved: {result}")
            print("✅ Stop complete")
            return result
        except Exception as e:
            print(f"   ⚠️  Error during cleanup: {e}")
            return None

    # ==================================================================
    # Definition methods  (always available, no model needed)
    # ==================================================================

    def fetch_hover_definition(self, word, src_lang, tgt_lang, on_ready):
        """Fetch simple definition in a background thread.
        Stores result on word.simple_result, then calls on_ready(word) on the BG thread."""
        def bg():
            result = fetch_definition(word.text, src_lang, tgt_lang)
            word.simple_result = result
            on_ready(word)
        threading.Thread(target=bg, daemon=True).start()

    def fetch_full_definition(self, word, src_lang, tgt_lang, on_ready):
        """Fetch simple + detailed definition in a background thread.
        Stores results on word, then calls on_ready(word) on the BG thread."""
        def bg():
            simple = fetch_definition(word.text, src_lang, tgt_lang)
            detail = fetch_details(word.text, src_lang, tgt_lang)
            word.simple_result = simple
            word.detail_result = detail
            on_ready(word)
        threading.Thread(target=bg, daemon=True).start()

    # ==================================================================
    # Anki methods  (always available, no model needed)
    # ==================================================================

    def ensure_anki_ready(self, on_ready):
        """Launch Anki + fetch deck list in a background thread.
        Calls on_ready(ok: bool, decks: list) on the BG thread."""
        def bg():
            ok = ensure_anki_running(timeout=15.0)
            decks = []
            if ok:
                try:
                    decks = get_deck_names()
                except Exception:
                    pass
            on_ready(ok, decks)
        threading.Thread(target=bg, daemon=True).start()

    def create_anki_deck(self, name, on_ready):
        """Create a new Anki deck in a background thread.
        Calls on_ready(result: dict) on the BG thread."""
        def bg():
            result = create_deck(name)
            on_ready(result)
        threading.Thread(target=bg, daemon=True).start()

    def save_to_anki(self, word, deck_name, src_lang, on_ready):
        """Build note fields and save to Anki in a background thread.
        Calls on_ready(result: dict) on the BG thread."""
        def bg():
            fields = build_note_fields(
                word.text, word.simple_result or {}, word.detail_result or {}, src_lang,
            )
            result = add_note(deck_name, fields)
            on_ready(result)
        threading.Thread(target=bg, daemon=True).start()
