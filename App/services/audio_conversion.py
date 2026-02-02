import numpy as np


class AudioConverter:
    """
    Converts raw PCM bytes (paInt16) from AudioCaptureLive into a Whisper-ready numpy array:
    - mono
    - float32 in range [-1..1]
    - 16kHz sample rate
    """

    @staticmethod
    def chunks_to_float_mono_16k(chunks: list[bytes], srcRate: int, channels: int) -> np.ndarray:
        if not chunks:
            return np.array([], dtype=np.float32)

        pcm_bytes = b"".join(chunks)

        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)

        # stereo -> mono
        if channels > 1:
            audio_int16 = audio_int16.reshape(-1, channels).mean(axis=1)

        # int16 -> float32 [-1..1]
        audio_f32 = audio_int16.astype(np.float32) / 32768.0

        # resample to 16000 if needed
        if srcRate != 16000:
            audio_f32 = AudioConverter._resampleTo16k(audio_f32, srcRate)

        return audio_f32

    @staticmethod
    def _resampleTo16k(audio: np.ndarray, srcRate: int) -> np.ndarray:
        # fast linear interpolation resample
        x_old = np.linspace(0, len(audio) / srcRate, num=len(audio), endpoint=False)
        n_new = int(len(audio) * 16000 / srcRate)
        x_new = np.linspace(0, len(audio) / srcRate, num=n_new, endpoint=False)
        return np.interp(x_new, x_old, audio).astype(np.float32)
