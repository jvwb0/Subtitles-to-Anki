import time
import wave
import pyaudiowpatch

# (Loopback = record the speaker output as input)'
# do not touch this file, it is working as intended
class AudioCaptureFixed:
    def __init__(self, duration=20, rate=48000, channels=2, chunk=1024, device=10):
        self.duration = duration
        self.rate = rate
        self.channels = channels
        self.chunk = chunk
        self.device = device
        self.filename = f"test_{int(time.time())}.wav"

    def recordWav(self, durationSec=None, filename=None) -> str:
        if durationSec is not None:
            self.duration = durationSec
        if filename is not None:
            self.filename = filename

        p = pyaudiowpatch.PyAudio()
        stream = p.open(
            format=pyaudiowpatch.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
            input_device_index=self.device,
        )

        frames = []
        secondsRecorded = 0.0
        secondsPerChunk = self.chunk / self.rate

        while secondsRecorded < self.duration:
            frames.append(stream.read(self.chunk))
            secondsRecorded += secondsPerChunk

        stream.stop_stream()
        stream.close()
        p.terminate()

        with wave.open(self.filename, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.rate)
            wf.writeframes(b"".join(frames))

        return self.filename
