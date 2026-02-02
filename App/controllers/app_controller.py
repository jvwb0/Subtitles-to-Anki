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
        self.live_recorder = AudioCaptureLive(device=config.device_id)
        self.live_transcriber = LiveTranscriber(self.whisper.model, self.live_recorder, config.language)
        self.is_recording = False
    
    def transcribe_wav(self, filename):
        audio = prepareAudioFromWav(filename)
        return self.whisper.transcribe(audio, self.config.language)
    
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
    
    def run_live_session(self, duration_sec=10.0, window_sec=2.0, tick_sleep=0.25, 
                         filename="live.wav", save_wav=True, on_words_callback=None):
        self.start_live(filename)
        start_time = time.time()
        
        def audio_capture():
            while self.is_recording:
                self.live_tick()
                time.sleep(0.001)
        
        def transcription_loop():
            while self.is_recording:
                try:
                    new_words = self.live_transcriber.tick(window_sec)
                    if new_words and on_words_callback:
                        on_words_callback(new_words)
                except Exception as e:
                    print(f"❌ Transcription error: {e}")
                time.sleep(tick_sleep)
        
        audio_thread = threading.Thread(target=audio_capture, daemon=True)
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
        
        elapsed = time.time() - start_time
        chunks = len(self.live_recorder.frames)
        print(f"\n📊 Recorded {chunks} chunks in {elapsed:.1f}s")
        
        self.stop_live(save_wav=save_wav)

    def run_manual_session(self, window_sec=2.0, tick_sleep=0.25, 
                           filename="live.wav", save_wav=True, on_words_callback=None):
        """
        Run live transcription session with manual stop (user presses Enter)
        
        Args:
            window_sec: Sliding window for transcription
            tick_sleep: Sleep between transcription checks
            filename: Output WAV filename
            save_wav: Whether to save the recording
            on_words_callback: Function to call when new words are detected
        """
        self.start_live(filename)
        start_time = time.time()
        
        # Audio capture thread
        def audio_capture():
            while self.is_recording:
                self.live_tick()
                time.sleep(0.001)
        
        # Transcription thread
        def transcription_loop():
            while self.is_recording:
                try:
                    new_words = self.live_transcriber.tick(window_sec)
                    if new_words and on_words_callback:
                        on_words_callback(new_words)
                except Exception as e:
                    print(f"❌ Transcription error: {e}")
                time.sleep(tick_sleep)
        
        # Start threads
        audio_thread = threading.Thread(target=audio_capture, daemon=True)
        trans_thread = threading.Thread(target=transcription_loop, daemon=True)
        
        audio_thread.start()
        trans_thread.start()
        
        # Wait for user to press Enter
        try:
            input()  # Blocks until user presses Enter
        except KeyboardInterrupt:
            pass
        
        # Stop everything
        self.is_recording = False
        trans_thread.join(timeout=2.0)
        audio_thread.join(timeout=2.0)
        
        # Stats
        elapsed = time.time() - start_time
        chunks = len(self.live_recorder.frames)
        print(f"\n📊 Recorded {chunks} chunks in {elapsed:.1f}s")
        
        self.stop_live(save_wav=save_wav)