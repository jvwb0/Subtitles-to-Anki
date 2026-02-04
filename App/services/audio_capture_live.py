import time
import wave
import pyaudiowpatch


class AudioCaptureLive:
    """
    Live recording (loopback/mic) with capped in-memory buffer.
    
    RAM protection: buffer capped at MAX_BUFFER_SECONDS to prevent unbounded growth.
    Crash protection: stream is stopped before threads join (prevents blocking read hang).
    """
    
    MAX_BUFFER_SECONDS = 300  # 5 minutes max in RAM
    
    def __init__(self, rate: int = 48000, channels: int = 2, chunk: int = 1024, device: int = 10):
        self.rate = rate
        self.channels = channels
        self.chunk = chunk
        self.device = device

        self.filename = None
        self.p = None
        self.stream = None

        self.frames: list[bytes] = []
        self._max_chunks = int((self.MAX_BUFFER_SECONDS * self.rate) / self.chunk)

    def start(self, filename: str | None = None):
        self.frames = []
        self.filename = filename or f"outputs/live_{int(time.time())}.wav"

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
        """
        Read one chunk from the stream.
        
        This is a BLOCKING call - if stream is stopped, it will raise an exception.
        """
        try:
            data = self.stream.read(self.chunk, exception_on_overflow=False)
            self.frames.append(data)
            
            # Cap the buffer - keep only last MAX_BUFFER_SECONDS
            if len(self.frames) > self._max_chunks:
                self.frames = self.frames[-self._max_chunks:]
            
            return data
        except Exception as e:
            # Expected during shutdown - stream.stop_stream() causes read() to fail
            return b""

    def getRecentChunks(self, seconds: float) -> list[bytes]:
        """Returns raw PCM chunks (bytes) for the last N seconds."""
        if seconds <= 0:
            return []

        chunks_needed = int((seconds * self.rate) / self.chunk)
        if chunks_needed <= 0:
            return []

        if len(self.frames) <= chunks_needed:
            return self.frames

        return self.frames[-chunks_needed:]

    def cleanup_and_save(self, save_wav: bool = True) -> str | None:
        """
        Cleanup resources and optionally save WAV.
        
        Called AFTER threads have joined (stream should already be stopped).
        
        Returns WAV filename if saved, None otherwise.
        """
        # Close stream if not already closed
        if self.stream is not None:
            try:
                if hasattr(self.stream, '_is_running') and self.stream._is_running:
                    self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                print(f"⚠️  Error closing stream: {e}")
            finally:
                self.stream = None

        # Terminate PyAudio
        if self.p is not None:
            try:
                self.p.terminate()
            except Exception as e:
                print(f"⚠️  Error terminating PyAudio: {e}")
            finally:
                self.p = None

        # Save WAV if requested
        if not save_wav or not self.frames:
            return None

        try:
            with wave.open(self.filename, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.rate)
                wf.writeframes(b"".join(self.frames))
            return self.filename
        except Exception as e:
            print(f"❌ Error saving WAV: {e}")
            return None