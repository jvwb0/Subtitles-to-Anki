# LiveTranscriber.py
from whisperTranscribeDemo import transcribeAudio
from AudioConversion import AudioWhispe


class LiveTranscriber:
    def __init__(self, model, recorder):
        self.model = model          # WhisperModel
        self.recorder = recorder    # AudioCaptureLive
        self.lastEmittedEnd = 0.0

    def reset(self):
        self.lastEmittedEnd = 0.0

    def tick(self, windowSec: float = 2.0) -> list:
        # 1) get last N seconds of raw PCM chunks (bytes)
        chunks = self.recorder.getRecentChunks(windowSec)
        if not chunks:
            return []

        # 2) convert raw PCM -> float32 mono 16k (Whisper-ready)
        audio = AudioWhispe.chunksToFloatMono16k(
            chunks,
            srcRate=self.recorder.rate,
            channels=self.recorder.channels
        )
        if audio.size == 0:
            return []

        # 3) Whisper -> Word objects
        words = transcribeAudio(self.model, audio)
        if not words:
            return []

        # 4) de-dupe: only emit words after what we've already emitted
        new_words = []
        cutoff = self.lastEmittedEnd - 0.05  # small overlap tolerance

        for w in words:
            if w.endTime > cutoff:
                new_words.append(w)

        if new_words:
            self.lastEmittedEnd = new_words[-1].endTime

        return new_words
