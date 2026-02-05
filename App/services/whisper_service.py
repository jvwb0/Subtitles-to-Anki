from faster_whisper import WhisperModel
from models.word import Word


class WhisperService:
    def __init__(self, model_size="tiny", use_gpu=False):
        self.model_size = model_size
        self.use_gpu = use_gpu

        # Determine device
        if use_gpu is None:
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    compute_type = "float32"
                else:
                    device = "cpu"
                    compute_type = "int8"
            except ImportError:
                device = "cpu"
                compute_type = "int8"
        elif use_gpu:
            device = "cuda"
            compute_type = "float32"
        else:
            device = "cpu"
            compute_type = "int8"

        print(f"Loading Whisper {model_size} on {device}...")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        print("✓ Model loaded!")

    def transcribe(self, audio, language="en") -> list[Word]:
        segments, _info = self.model.transcribe(
            audio,
            language=language,
            task="transcribe",
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