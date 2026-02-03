import wave
import numpy as np
from services.audio_conversion import AudioConverter


def prepareAudioFromWav(filename: str) -> np.ndarray:
    """Load a WAV file and return a Whisper-ready float32 mono 16 kHz array."""
    with wave.open(filename, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        return AudioConverter.chunks_to_float_mono_16k(
            [raw], srcRate=wf.getframerate(), channels=wf.getnchannels()
        )