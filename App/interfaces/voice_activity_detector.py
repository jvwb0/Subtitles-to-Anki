"""Contract for a stateful, frame-at-a-time voice activity detector."""

from abc import ABC, abstractmethod

import numpy as np


class IVoiceActivityDetector(ABC):
    @abstractmethod
    def reset(self):
        """Reset internal state — call when starting a new audio stream."""
        raise NotImplementedError

    @abstractmethod
    def speech_prob(self, frame: np.ndarray) -> float:
        """Speech probability [0..1] for one audio frame."""
        raise NotImplementedError
