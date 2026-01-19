import numpy
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

def init_model():
    return WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

def record_loopback(duration_sec: int) -> bytes:
    p = pyaudiowpatch.PyAudio()

    stream = p.open(
        format=pyaudiowpatch.paInt16,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
        input_device_index=DEVICE
    )

    frames = []

    for _ in range(int(RATE / CHUNK * duration_sec)):
        frames.append(stream.read(CHUNK))

    stream.stop_stream()
    stream.close()
    p.terminate()

    return b"".join(frames)
