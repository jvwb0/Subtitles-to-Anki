import numpy as np
import wave
from Word_obj import Word
from faster_whisper import WhisperModel

# loopback recording settings
DEVICE = 10
RATE = 48000
CHANNELS = 2
CHUNK = 1024
DURATION = 10

MODEL_SIZE = "small" 
#LANGUAGE = "pt" # Portuguese - we can change this as needed

def bytesToNumpyArray(data: bytes) -> np.ndarray:
    audio = np.frombuffer(data, dtype=np.int16)
    audio = audio.reshape(-1, CHANNELS).mean(axis=1)  # stereo → mono
    audio = audio.astype(np.float32) / 32768.0
    return audio

def loadWavAsBytes(filename: str) -> bytes:
    with wave.open(filename, "rb") as wf:
        return wf.readframes(wf.getnframes())
    
def transcribeAudio(audio: np.ndarray) ->  list[Word]:
    model = WhisperModel(MODEL_SIZE, device="cpu",compute_type="int8",)

    segments, info = model.transcribe(
        audio,
        beam_size=10, 
        best_of=5, # keep an eye on unepxpected keyword, if os we just take this out
        vad_filter=True,
        word_timestamps=True)

    print("Detected language:", info.language)
    word: list[Word] = []
    for segment in segments:
        for w in segment.words:
            print(w.word, w.start, w.end, )
            word.append(Word(w.word, w.start, w.end))

    return word
    
def resampleAudio(audio: np.ndarray, srcRate: int) -> np.ndarray:
    if srcRate == 16000:
        return audio

    xOld = np.linspace(0, len(audio) / srcRate, num=len(audio), endpoint=False)
    nNew = int(len(audio) * 16000 / srcRate)
    xNew = np.linspace(0, len(audio) / srcRate, num=nNew, endpoint=False)

    return np.interp(xNew, xOld, audio).astype(np.float32)


data = loadWavAsBytes("umalendachamadapinto.wav")
audio = bytesToNumpyArray(data)
audio = resampleAudio(audio, RATE)
transcribeAudio(audio)