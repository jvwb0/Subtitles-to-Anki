import time
import threading
from faster_whisper import WhisperModel

from whisperTranscribeDemo import prepareAudioFromWav, transcribeAudio
from AudioCaptureFixed import AudioCaptureFixed
from AudioCaptureLive import AudioCaptureLive
from LiveTranscriber import LiveTranscriber


class TranscriptionController:
    def __init__(self, modelSize="small", device=10, use_gpu: bool | None = None):
        self.device = device

        # Decide where to run the Whisper model. If use_gpu is None try to auto-detect CUDA.
        model_device = "cpu"
        compute_type = "int8"
        if use_gpu is None:
            try:
                import torch

                if torch.cuda.is_available():
                    model_device = "cuda"
                    compute_type = "float16"
            except Exception:
                model_device = "cpu"
        else:
            if use_gpu:
                model_device = "cuda"
                compute_type = "float16"

        # Load Whisper model
        self.model = WhisperModel(modelSize, device=model_device, compute_type=compute_type)

        self.fixedRecorder = AudioCaptureFixed(device=self.device)
        self.liveRecorder = AudioCaptureLive(device=self.device)

        # live transcription engine (separate responsibility)
        self.liveTranscriber = LiveTranscriber(self.model, self.liveRecorder)

        self.isRecording = False

    # =========================
    # FILE-BASED TRANSCRIPTION
    # =========================

    def transcribeWav(self, filename):
        audio = prepareAudioFromWav(filename)
        return transcribeAudio(self.model, audio)

    def recordAndTranscribe(self, durationSec, filename="record.wav"):
        # record N seconds then transcribe
        wav_path = self.fixedRecorder.recordWav(durationSec, filename)
        return self.transcribeWav(wav_path)

    # =========================
    # LIVE RECORDING CONTROL
    # =========================

    def startLive(self, filename="live.wav"):
        # Starts the microphone / loopback stream
        self.liveRecorder.start(filename)
        self.liveTranscriber.reset()
        self.isRecording = True

    def liveTick(self):
        # Read one audio chunk from the live stream
        if self.isRecording:
            self.liveRecorder.readChunk()

    def stopLive(self, saveWav: bool = True):
        # Stop recording and optionally finalize WAV file
        self.isRecording = False
        return self.liveRecorder.stop(saveWav=saveWav)

    # =========================
    # LIVE TRANSCRIPTION
    # =========================

    def liveTranscribeTick(self, windowSec: float = 2.0) -> list:
        # Transcribe the last N seconds while recording
        if not self.isRecording:
            return []
        return self.liveTranscriber.tick(windowSec)

    def runLiveSession(
        self,
        durationSec: float = 10.0,
        windowSec: float = 2.0,
        tickSleep: float = 0.25,
        filename: str = "live.wav",
        saveWav: bool = True,
        onWords=None
    ):
        """
        Full live session with THREADING:
        - Audio capture thread runs continuously (never blocked)
        - Main thread transcribes in background
        - Words emitted live via callback
        """
        self.startLive(filename)
        self.isRecording = True

        start = time.time()

        # Thread that continuously reads audio (never blocked by transcription)
        def audioCapture():
            while self.isRecording:
                self.liveTick()
                time.sleep(0.001)

        audio_thread = threading.Thread(target=audioCapture, daemon=True)
        audio_thread.start()

        # Separate transcription thread so model inference doesn't delay audio reads
        def transcriptionLoop():
            while self.isRecording:
                try:
                    new_words = self.liveTranscriber.tick(windowSec)
                    if new_words and onWords:
                        onWords(new_words)
                except Exception as e:
                    print(f"❌ Transcription error: {e}")
                time.sleep(tickSleep)

        trans_thread = threading.Thread(target=transcriptionLoop, daemon=True)
        trans_thread.start()

        # Wait for the requested duration while background threads run
        try:
            while time.time() - start < durationSec:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass

        # Stop everything
        self.isRecording = False
        trans_thread.join(timeout=2.0)
        audio_thread.join(timeout=2.0)

        elapsed = time.time() - start
        chunks_recorded = len(self.liveRecorder.frames)
        print(f"\n📊 Recorded {chunks_recorded} chunks in {elapsed:.1f}s")

        self.stopLive(saveWav=saveWav)
