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
        chunks = self.recorder.getRecentChunks(windowSec)
        if not chunks:
            return []
    
        audio = AudioWhispe.chunksToFloatMono16k(
            chunks,
            srcRate=self.recorder.rate,
            channels=self.recorder.channels
        )
        if audio.size == 0:
            return []
    
        words = transcribeAudio(self.model, audio)
        if not words:
            return []
    
        # --- make timestamps absolute ---
        # total recorded seconds so far (based on how many chunks we have)
        total_chunks = len(self.recorder.frames)
        recorded_sec = (total_chunks * self.recorder.chunk) / self.recorder.rate
    
        # this window covers [window_start .. recorded_sec]
        window_start = max(0.0, recorded_sec - windowSec)
    
        # shift word times from "window-relative" to "absolute"
        for w in words:
            w.startTime += window_start
            w.endTime += window_start
    
        # --- de-dupe using absolute time ---
        new_words = []
        cutoff = self.lastEmittedEnd - 0.05
    
        for w in words:
            if w.endTime > cutoff:
                new_words.append(w)
    
        if new_words:
            self.lastEmittedEnd = new_words[-1].endTime
    
        return new_words
