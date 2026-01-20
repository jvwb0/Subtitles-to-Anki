import numpy as np
import wave
import pyaudiowpatch
from faster_whisper import WhisperModel

# loopback recording settings
DEVICE = 10
RATE = 48000
CHANNELS = 2
CHUNK = 1024
DURATION = 5

MODEL_SIZE = "tiny" 
LANGUAGE = "pt" # Portuguese - we can change this as needed

def bytesToNumpyArray(data: bytes) -> np.ndarray:
    audio = np.frombuffer(data, dtype=np.int16)
    audio = audio.reshape(-1, CHANNELS).mean(axis=1)  # stereo → mono
    audio = audio.astype(np.float32) / 32768.0
    return audio

def transcribeAudio(audio: np.ndarray) -> None:
    model = WhisperModel(MODEL_SIZE, device="cpu",compute_type="int8",)

    segments, info = model.transcribe(audio)

    print("Detected language:", info.language)
    for segment in segments:
        print(segment.text)

def loadWavAsBytes(filename: str) -> bytes:
    with wave.open(filename, "rb") as wf:
        return wf.readframes(wf.getnframes())

data = loadWavAsBytes("test_1768909877.wav")
audio = bytesToNumpyArray(data)
transcribeAudio(audio)