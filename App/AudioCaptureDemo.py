#import sounddevice as sd
import numpy 
import wave
from faster_whisper import WhisperModel
import pyaudiowpatch #because sounddevice doesnt supprot loopback recording on windows WASAPI
'(Loopback = record the speaker output as input)'

'first we need to install Sounddevice to record audio from the screen,'
' then numPy to save audio data as an array,'
' and finally we will install Whisper to transcribe the audio into text'
'all this in a virtual environment to keep our dependencies organized'

DURATION = 5          # seconds
RATE = 48000
CHANNELS = 2
CHUNK = 1024
DEVICE = 10  # Speakers : python -m pyaudiowpatch (to list devices)
frames = []

p = pyaudiowpatch.PyAudio()
stream = p.open(
    format=pyaudiowpatch.paInt16,
    channels=CHANNELS,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK,
    input_device_index=DEVICE)

print("\nRecording system audio...\n")

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