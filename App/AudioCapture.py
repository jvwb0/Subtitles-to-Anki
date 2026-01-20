import time
import wave
import pyaudiowpatch #because sounddevice doesnt supprot loopback recording on windows WASAPI
# (Loopback = record the speaker output as input)'

# first we need to install Sounddevice to record audio from the screen,'
# then numPy to save audio data as an array,'
# and finally we will install Whisper to transcribe the audio into text'
# all this in a virtual environment to keep our dependencies organized'

class AudioCapture:
    def __init__(self, rate: int = 48000, channels: int = 2, chunk: int = 1024, device: int = 10):
        self.rate = rate
        self.channels = channels
        self.chunk = chunk
        self.device = device # Speakers : python -m pyaudiowpatch (to list devices)

        self.filename = None
        self.p = None
        self.stream = None
        self.frames = []

    def start(self, filename = None):
        self.frames = []
        self.filename = filename or  f"test_{int(time.time())}.wav"

        self.p = pyaudiowpatch.PyAudio()
        self.stream = self.p.open(
            format=pyaudiowpatch.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
            input_device_index=self.device
            )

    def readChunk(self):
        self.frames.append(self.stream.read(self.chunk))

    def stop(self) -> str:
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

        with wave.open(self.filename, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.rate)
            wf.writeframes(b"".join(self.frames)) # raw PCM bytes

        return self.filename        
    
# out put from demo was 4096 bytes per chunk,
# each chunk is 1024 samples, each sample is 2 bytes (16 bit audio), stereo = 2 channels
# 1024 samples * 2 bytes * 2 channels = 4096 bytes
# so demo was a sucess, we recorded audio, verified the correct data sizes
# now we can move on to transcribing the audio with Whisper