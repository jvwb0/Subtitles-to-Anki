import os
from random import sample
import sys
import argparse
import queue
import sounddevice as sd
import numpy
import wave


'first we need to install Sounddevice to record audio from the screen,'
' then numPy to save audio data as an array,'
' and finally we will install Whisper to transcribe the audio into text'
'all this in a virtual environment to keep our dependencies organized'
import sounddevice as sd
import numpy as np
import wave
import pyaudiowpatch as pyaudio

DURATION = 5          # seconds
RATE = 48000
CHANNELS = 2
CHUNK = 1024

LOOPBACK_DEVICE_INDEX = 10  # Speakers (Realtek) [Loopback]

p = pyaudio.PyAudio()

stream = p.open(
    format=pyaudio.paInt16,
    channels=CHANNELS,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK,
    input_device_index=LOOPBACK_DEVICE_INDEX,
)

frames = []

print("Recording system audio...")
for _ in range(int(RATE / CHUNK * DURATION)):
    frames.append(stream.read(CHUNK))

stream.stop_stream()
stream.close()
p.terminate()

with wave.open("test.wav", "wb") as wf:
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(2)  # 16-bit
    wf.setframerate(RATE)
    wf.writeframes(b"".join(frames))

print("Saved test.wav")