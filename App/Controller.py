from faster_whisper import WhisperModel
from Word_obj import Word
from whisperTranscribeDemo import prepareAudioFromWav, transcribeAudio
from AudioCapture import AudioCapture


class TranscriptionController:
    def __init__(self, modelSize: str = "small", device: int = 10):
        self.model = WhisperModel(modelSize, device="cpu", compute_type="int8")
        self.recorder = AudioCapture(device=device)  # Set your desired audio device index here
        self.isRecording = False

    def startCapture(self, filename=None):
        self.recorder.start(filename)
        self.isRecording = True

    def stopAndTranscribe(self):
        self.isRecording = False
        wav_path = self.recorder.stop()
        audio = prepareAudioFromWav(filename= wav_path)
        return transcribeAudio(self.model, audio)

    def captureTick(self):
        if self.isRecording:
            self.recorder.readChunk()