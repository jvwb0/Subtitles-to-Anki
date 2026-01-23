from faster_whisper import WhisperModel
from whisperTranscribeDemo import prepareAudioFromWav, transcribeAudio
from AudioCaptureFixed import AudioCaptureFixed
from AudioCaptureLive import AudioCaptureLive

class TranscriptionController:
    def __init__(self, modelSize="small", device=10):
        self.device = device
        self.model = WhisperModel(modelSize, device="cpu", compute_type="int8")

        self.fixedRecorder = AudioCaptureFixed(device=self.device)
        self.liveRecorder = AudioCaptureLive(device=self.device)

        self.isRecording = False

    def transcribeWav(self, filename):
        audio = prepareAudioFromWav(filename)
        return transcribeAudio(self.model, audio)

    # FEATURE 1: record N seconds then transcribe
    def recordAndTranscribe(self, durationSec, filename="record.wav"):
        wav_path = self.fixedRecorder.recordWav(durationSec, filename)
        return self.transcribeWav(wav_path)

    # FEATURE 2: live session start/stop (transcribe on stop for now)
    def startLive(self, filename="live.wav"):
        self.liveRecorder.start(filename)
        self.isRecording = True

    def liveTick(self):
        if self.isRecording:
            self.liveRecorder.readChunk()

    
    def stopLive(self) -> str:
        self.isRecording = False
        return self.liveRecorder.stop()

    def stopLiveAndTranscribe(self):
        wav_path = self.stopLive()
        return self.transcribeWav(wav_path)

