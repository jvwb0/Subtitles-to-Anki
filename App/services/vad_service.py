"""
Silero VAD — real-time voice activity detection.

Silero VAD is a ~2 MB LSTM-based model that runs at 16 kHz and processes
512-sample frames (~32 ms each) in < 1 ms on CPU.

It is *stateful*: the LSTM hidden state is preserved between consecutive
frames of the same audio stream, and must be reset when a new stream starts.

Runs on ONNX Runtime (not PyTorch) so the app doesn't need to install torch
just for this small model — ctranslate2 (used for Whisper) has its own
independent CUDA support and doesn't need torch either.
"""

from pathlib import Path

import numpy as np
import onnxruntime as ort
import requests

from interfaces.voice_activity_detector import IVoiceActivityDetector

_MODEL_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/"
    "src/silero_vad/data/silero_vad.onnx"
)
_CACHE_PATH = Path.home() / ".cache" / "silero_vad" / "silero_vad.onnx"


def _ensure_model_downloaded() -> Path:
    """Download the ONNX weights once and cache them under ~/.cache."""
    if _CACHE_PATH.exists():
        return _CACHE_PATH
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(_MODEL_URL, timeout=30)
    response.raise_for_status()
    _CACHE_PATH.write_bytes(response.content)
    return _CACHE_PATH


class VadService(IVoiceActivityDetector):
    SAMPLE_RATE = 16000
    FRAME_SIZE = 512          # 32 ms @ 16 kHz
    _CONTEXT_SIZE = 64        # required trailing samples carried between calls

    def __init__(self):
        print("  Loading Silero VAD…", end=" ", flush=True)
        try:
            model_path = _ensure_model_downloaded()
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            self._session = ort.InferenceSession(
                str(model_path), sess_options=opts, providers=["CPUExecutionProvider"]
            )
            self.reset()
            print("✓")
        except Exception as e:
            raise RuntimeError(
                "Failed to load Silero VAD. Internet is required on first run "
                f"(model is cached afterwards).  Original error: {e}"
            )

    def reset(self):
        """Reset internal LSTM state — call when starting a new audio stream."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self._CONTEXT_SIZE), dtype=np.float32)

    def speech_prob(self, frame: np.ndarray) -> float:
        """
        Speech probability [0..1] for one 512-sample 16 kHz frame.
        Preserves LSTM state between calls.
        """
        x = frame.astype(np.float32).reshape(1, -1)
        x = np.concatenate([self._context, x], axis=1)

        ort_inputs = {
            "input": x,
            "state": self._state,
            "sr": np.array(self.SAMPLE_RATE, dtype=np.int64),
        }
        out, state = self._session.run(None, ort_inputs)

        self._state = state
        self._context = x[:, -self._CONTEXT_SIZE:]
        return float(out.item())
