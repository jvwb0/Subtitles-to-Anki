# LiveTranscriber.py
from tabnanny import check
from utils.audio_utils import transcribeAudio
from models.word import Word
from services.audio_conversion import AudioConverter

class LiveTranscriber:
    def __init__(self, model, recorder, language: str = "en"):
        self.model = model          # WhisperModel
        self.recorder = recorder    # AudioCaptureLive
        self.language = language    # Language code (e.g., "en", "es", "fr")
        self.lastEmittedEnd = 0.0
        self.seen_words = {}  # {word_text: last_end_time}        

    def reset(self):
        """clears the de-duplication tracking when starting a new recording session."""
        self.lastEmittedEnd = 0.0
        self.seen_words = {}

    def tick(self, windowSec = 2.0) :
        chunks = self.recorder.getRecentChunks(windowSec)
        if not chunks:
            return []
    
        audio = AudioConverter.chunks_to_float_mono_16k(
            chunks,
            srcRate=self.recorder.rate,
            channels=self.recorder.channels
        )
        if audio.size == 0:
            return []
    
        words = transcribeAudio(self.model, audio, self.language)
        if not words:
            return []
    
        # --- make timestamps absolute ---
        # total recorded seconds so far (based on how many chunks we have)
        total_chunks = len(self.recorder.frames)
        recorded_sec = (total_chunks * self.recorder.chunk) / self.recorder.rate
        window_start = max(0.0, recorded_sec - windowSec) # this window covers [window_start .. recorded_sec]
    
        # shift word times from "window-relative" to "absolute"
        for w in words:
            w.startTime += window_start
            w.endTime += window_start
    
           # De-dupe using text + time proximity
        new_words = []
        
        for w in words:
            word_key = w.text.lower().strip()
            
            # Skip if we've seen this exact word very recently (within 0.5s)
            if word_key in self.seen_words:
                last_time = self.seen_words[word_key]
                if w.endTime - last_time < 0.9:
                    continue
            # Skip if it's the same as the last emitted word
            if len(new_words) > 0 and w.text.lower() == new_words[-1].text.lower():
                continue  
            # Also skip if it's before our cutoff
            if w.endTime <= self.lastEmittedEnd :
                continue
            
            new_words.append(w)
            self.seen_words[word_key] = w.endTime
    
        if new_words:
            self.lastEmittedEnd = new_words[-1].endTime
        
        # Clean up old entries from seen_words (keep last 5 seconds)
        cutoff_time = recorded_sec - 5.0
        self.seen_words = {k: v for k, v in self.seen_words.items() if v > cutoff_time}
    
        return new_words
