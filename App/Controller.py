from faster_whisper import WhisperModel
from Word_obj import Word
from whisperTranscribeDemo import prepareAudioFromWav, transcribeAudio


class TranscriptionController:
    def __init__(self, modelSize: str = "small"):
        self.model = WhisperModel(modelSize, device="cpu", compute_type="int8")

    def transcribeWav(self, filename: str) -> list[Word]:
        audio = prepareAudioFromWav(filename)
        return transcribeAudio(self.model, audio)

