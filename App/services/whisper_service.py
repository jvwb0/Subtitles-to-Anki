import ctranslate2
from faster_whisper import WhisperModel

from interfaces.transcription_engine import ITranscriptionEngine
from models.word import Word
from utils.text_utils import strip_punct


class WhisperService(ITranscriptionEngine):
    # Whisper's own "this segment is garbage" thresholds
    NO_SPEECH_THRESHOLD = 0.6
    LOW_LOGPROB = -1.0
    MAX_COMPRESSION_RATIO = 2.4   # highly repetitive text compresses too well
    MAX_WORD_REPEATS = 3          # "no no no no no" loops are almost always hallucinated

    # Subtitle-credit text Whisper invents on silence/music (from its training data)
    HALLUCINATED_PHRASES = ("amara.org", "legendas pela comunidade", "subtitulos por la comunidad")

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

    def transcribe(self, audio, language="en", task="transcribe", prompt=None) -> list[Word]:
        segments, _info = self.model.transcribe(
            audio,
            language=language,
            task=task,
            beam_size=5,
            best_of=2,
            vad_filter=True,
            word_timestamps=True,
            condition_on_previous_text=False,
            no_speech_threshold=self.NO_SPEECH_THRESHOLD,
            initial_prompt=prompt or None,
        )

        words: list[Word] = []

        for segment in segments:
            if not getattr(segment, "words", None):
                continue
            if self._is_hallucination(segment):
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
    
        return self._drop_repeat_loops(words)

    @classmethod
    def _is_hallucination(cls, segment) -> bool:
        """True for segments Whisper most likely invented (silence, music, loops)."""
        text = (getattr(segment, "text", "") or "").lower()
        if any(phrase in text for phrase in cls.HALLUCINATED_PHRASES):
            return True
        no_speech = getattr(segment, "no_speech_prob", None) or 0.0
        logprob = getattr(segment, "avg_logprob", None)
        if no_speech > cls.NO_SPEECH_THRESHOLD and logprob is not None and logprob < cls.LOW_LOGPROB:
            return True
        compression = getattr(segment, "compression_ratio", None)
        return compression is not None and compression > cls.MAX_COMPRESSION_RATIO

    @classmethod
    def _drop_repeat_loops(cls, words: list[Word]) -> list[Word]:
        """Keep at most MAX_WORD_REPEATS identical words in a row."""
        kept: list[Word] = []
        run = 0
        for word in words:
            key = strip_punct(word.text)
            same = bool(kept) and key == strip_punct(kept[-1].text)
            run = run + 1 if same else 1
            if run <= cls.MAX_WORD_REPEATS:
                kept.append(word)
        return kept
