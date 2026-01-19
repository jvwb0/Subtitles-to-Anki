import numpy
import wave
import pyaudiowpatch
from faster_whisper import WhisperModel

# loopback recording settings
DEVICE = 10
CHANNEL = 2
RATE = 48000
CHUNK = 1024

MODEL_SIZE = "tiny" # model size: tiny, base, small, medium, large"

model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

p = pyaudiowpatch.PyAudio()
stream = p.open(
    format=pyaudiowpatch.paInt16,
    channels=CHANNEL,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK,
    input_device_index=DEVICE)

frames = []

print("\nRecording system audio...\n")

stream.stop_stream()
stream.close()