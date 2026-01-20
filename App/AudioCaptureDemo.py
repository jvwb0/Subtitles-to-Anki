import numpy 
import time
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

#filename = f"test{counter}.wav"
filename = f"test_{int(time.time())}.wav"

def openLoopbackStream(p: pyaudiowpatch.PyAudio):
    return p.open(
        format=pyaudiowpatch.paInt16,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
        input_device_index=DEVICE,)

def recordFrames(stream, durationSec: int) -> list[bytes]:
    frames: list[bytes] = []
    for _ in range(int(RATE / CHUNK * durationSec)):
        frames.append(stream.read(CHUNK))
    return frames

def saveWav(frames: list[bytes]) -> None:
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))

    print("Saved WAV file", filename)

def main():
    p = pyaudiowpatch.PyAudio()
    stream = openLoopbackStream(p)

    print("\nRecording System Audio.........\n")
    frames = recordFrames(stream, DURATION)

    stream.stop_stream()
    stream.close()
    p.terminate()

    saveWav(frames)

if __name__ == "__main__": main()