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
    audio = np.reshape(audio, (-1, CHANNELS).mean(axis=1))  # convert to mono by averaging channels
    audio = audio.astype(np.float32) / 32768.0
    return audio