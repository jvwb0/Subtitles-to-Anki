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
            if not segment.words:
                continue
            for w in segment.words:
                words.append(Word(w.word.strip(), float(w.start), float(w.end)))
        return words