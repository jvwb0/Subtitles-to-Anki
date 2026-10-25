import ctranslate2
from faster_whisper import WhisperModel

from interfaces.transcription_engine import ITranscriptionEngine
from models.word import Word


class WhisperService(ITranscriptionEngine):
    def __init__(self, model_size="tiny", use_gpu=False):
        self.model_size = model_size
        self.use_gpu = use_gpu

        # Determine device: explicit True/False wins, None means auto-detect
        if use_gpu is None:
            use_gpu = ctranslate2.get_cuda_device_count() > 0
        device = "cuda" if use_gpu else "cpu"
        compute_type = "float16" if use_gpu else "int8"

        print(f"Loading Whisper {model_size} on {device}...")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        print("✓ Model loaded!")

    def transcribe(self, audio, language="en", task="transcribe") -> list[Word]:
        segments, _info = self.model.transcribe(
            audio,
            language=language,
            task=task,
            beam_size=5,
            best_of=2,
            vad_filter=True,
            word_timestamps=True,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )
    
        words: list[Word] = []
    
        for segment in segments:
            if not getattr(segment, "words", None):
                continue
            
            # Segment-level confidence-ish signals (may or may not exist)
            seg_avg_logprob = getattr(segment, "avg_logprob", None)
            seg_no_speech_prob = getattr(segment, "no_speech_prob", None)
    
            for w in segment.words:
                # faster-whisper MAY expose this
                w_prob = getattr(w, "probability", None)
    
                words.append(
                    Word(
                        text=w.word.strip(),
                        startTime=float(w.start),
                        endTime=float(w.end),
                        confidence=w_prob,
                        avg_logprob=seg_avg_logprob,
                        no_speech_prob=seg_no_speech_prob,
                    )
                )
    
        return words