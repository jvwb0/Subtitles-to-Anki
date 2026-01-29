import time
import wave
import pyaudiowpatch  # sounddevice doesn't support WASAPI loopback on Windows


# Live recording (loopback/mic) into an in-memory buffer, then optionally write WAV.
class AudioCaptureLive:
    def __init__(self, rate: int = 48000, channels: int = 2, chunk: int = 1024, device: int = 10):
        self.rate = rate
        self.channels = channels
        self.chunk = chunk
        self.device = device  # use: python -m pyaudiowpatch (to list devices)

        self.filename = None
        self.p = None
        self.stream = None

        # buffer of raw PCM chunks (bytes)
        self.frames: list[bytes] = []

    def start(self, filename: str | None = None):
        self.frames = []
        self.filename = filename or f"live_{int(time.time())}.wav"

        self.p = pyaudiowpatch.PyAudio()
        self.stream = self.p.open(
            format=pyaudiowpatch.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
            input_device_index=self.device
        )

    def readChunk(self) -> bytes:
        data = self.stream.read(self.chunk, exception_on_overflow=False)
        self.frames.append(data)
        return data

    def getRecentChunks(self, seconds: float) -> list[bytes]:
        # Returns raw PCM chunks (bytes) for the last N seconds.
        if seconds <= 0:
            return []

        chunks_needed = int((seconds * self.rate) / self.chunk)
        if chunks_needed <= 0:
            return []

        if len(self.frames) <= chunks_needed:
            return self.frames

        return self.frames[-chunks_needed:]

    def stop(self, saveWav: bool = True) -> str | None:
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if self.p is not None:
            self.p.terminate()
            self.p = None

        if not saveWav:
            return None

        with wave.open(self.filename, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.rate)
            wf.writeframes(b"".join(self.frames))  # raw PCM bytes

        return self.filename
