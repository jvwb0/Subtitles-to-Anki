class Word:
    """
    Lightweight word token used across the app.

    confidence:
        Per-word probability (0..1) if backend provides it.
        None if unavailable.

    avg_logprob:
        Segment-level average log probability (Whisper-style fallback signal).

    no_speech_prob:
        Segment-level probability that this segment is silence.
    """
    def __init__(
        self,
        text: str,
        startTime: float,
        endTime: float,
        confidence: float | None = None,
        avg_logprob: float | None = None,
        no_speech_prob: float | None = None,
    ):
        self.text = text.strip()
        self.startTime = float(startTime)
        self.endTime = float(endTime)

        self.confidence = float(confidence) if confidence is not None else None
        self.avg_logprob = float(avg_logprob) if avg_logprob is not None else None
        self.no_speech_prob = float(no_speech_prob) if no_speech_prob is not None else None