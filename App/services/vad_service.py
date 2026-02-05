"""
Silero VAD — real-time voice activity detection.

Silero VAD is a ~2 MB LSTM-based model that runs at 16 kHz and processes
512-sample frames (~32 ms each) in < 1 ms on CPU.

It is *stateful*: the LSTM hidden state is preserved between consecutive
frames of the same audio stream, and must be reset when a new stream starts.
"""

import torch
import numpy as np


class VadService:
    SAMPLE_RATE = 16000
    FRAME_SIZE  = 512          # 32 ms @ 16 kHz

    def __init__(self):
        print("  Loading Silero VAD…", end=" ", flush=True)
        try:
            self._model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self._model.eval()
            print("✓")
        except Exception as e:
            raise RuntimeError(
                "Failed to load Silero VAD. Internet is required on first run "
                f"(model is cached afterwards).  Original error: {e}"
            )

    def reset(self):
        """Reset internal LSTM state — call when starting a new audio stream."""
        self._model.reset_states()

    @torch.no_grad()
    def speech_prob(self, frame: np.ndarray) -> float:
        """
        Speech probability [0..1] for one 512-sample 16 kHz frame.
        Preserves LSTM state between calls.
        """
        tensor = torch.FloatTensor(frame.astype(np.float32))
        return self._model(tensor, sr=self.SAMPLE_RATE).item()
