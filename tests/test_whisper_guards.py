import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "App"))
sys.modules.setdefault("pyaudiowpatch", types.ModuleType("pyaudiowpatch"))

# whisper_service imports faster_whisper at module level; the guards don't need it
sys.modules.setdefault("faster_whisper", types.SimpleNamespace(WhisperModel=object))

from models.word import Word
from services.whisper_service import WhisperService


def segment(text="hello there", no_speech=0.0, logprob=-0.3, compression=1.2):
    return types.SimpleNamespace(text=text, no_speech_prob=no_speech,
                                 avg_logprob=logprob, compression_ratio=compression)


def run_of(*tokens):
    return [Word(text=t, startTime=i * 0.2, endTime=i * 0.2 + 0.1) for i, t in enumerate(tokens)]


class HallucinationGuardTests(unittest.TestCase):
    def test_normal_segment_kept(self):
        self.assertFalse(WhisperService._is_hallucination(segment()))

    def test_silence_with_low_confidence_dropped(self):
        self.assertTrue(WhisperService._is_hallucination(segment(no_speech=0.9, logprob=-1.5)))

    def test_high_no_speech_but_confident_text_kept(self):
        self.assertFalse(WhisperService._is_hallucination(segment(no_speech=0.9, logprob=-0.2)))

    def test_repetitive_segment_dropped(self):
        self.assertTrue(WhisperService._is_hallucination(segment(compression=3.5)))

    def test_subtitle_credit_dropped(self):
        self.assertTrue(WhisperService._is_hallucination(segment(text="Subtitles by the Amara.org community")))

    def test_repeat_loops_are_collapsed(self):
        kept = WhisperService._drop_repeat_loops(run_of(*["no"] * 8, "way"))
        self.assertEqual([w.text for w in kept], ["no", "no", "no", "way"])

    def test_normal_repeats_survive(self):
        kept = WhisperService._drop_repeat_loops(run_of("very", "very", "good"))
        self.assertEqual(len(kept), 3)


if __name__ == "__main__":
    unittest.main()
