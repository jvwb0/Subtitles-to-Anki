import time
from faster_whisper import WhisperModel

from whisperTranscribeDemo import prepareAudioFromWav, transcribeAudio
from AudioCaptureFixed import AudioCaptureFixed
from AudioCaptureLive import AudioCaptureLive
from LiveTranscriber import LiveTranscriber


class TranscriptionController:
    def __init__(self, modelSize="small", device=10):
        self.device = device

        # Whisper model (CPU for now – GPU is future upgrade)
        self.model = WhisperModel(modelSize, device="cpu", compute_type="int8")

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

    def runLiveSession(self, durationSec: float = 10.0, windowSec: float = 2.0, tickSleep: float = 0.25, filename: str = "live.wav", saveWav: bool = True):
        """
        Full live session:
        - starts recording
        - transcribes while recording
        - stops recording
        - returns all Word objects
        """
        self.startLive(filename)

        start = time.time()
        all_words = []

        while time.time() - start < durationSec:
            self.liveTick()
            all_words.extend(self.liveTranscribeTick(windowSec))
            time.sleep(tickSleep)

        self.stopLive(saveWav=saveWav)
        return all_words
