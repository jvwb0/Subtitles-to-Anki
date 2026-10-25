import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "App"))
sys.modules.setdefault("pyaudiowpatch", types.ModuleType("pyaudiowpatch"))

from models.word import Word
from services.caption_builder import CaptionBuilder
from services.partial_stabilizer import PartialStabilizer


def words(text, start=0.0, step=0.4):
    return [Word(text=t, startTime=start + i * step, endTime=start + i * step + 0.3)
            for i, t in enumerate(text.split())]


def texts(ws):
    return [w.text for w in ws]


class PartialStabilizerTests(unittest.TestCase):
    def test_first_hypothesis_is_shown_as_is(self):
        stab = PartialStabilizer()
        self.assertEqual(texts(stab.update(words("hello wor"))), ["hello", "wor"])

    def test_agreed_words_lock_and_stop_changing(self):
        stab = PartialStabilizer()
        stab.update(words("I have 100 or"))
        stab.update(words("I have 100 or 200"))     # "I have 100 or" now agreed twice
        shown = stab.update(words("I have $100 or $200 dollars"))  # reword of locked region
        self.assertEqual(texts(shown)[:3], ["I", "have", "100"])
        self.assertNotIn("$100", texts(shown))

    def test_newest_word_is_never_locked(self):
        stab = PartialStabilizer()
        stab.update(words("hello"))
        stab.update(words("hello"))
        shown = stab.update(words("hello"))
        self.assertEqual(texts(shown), ["hello"])
        self.assertEqual(texts(stab.update(words("hello there"))), ["hello", "there"])

    def test_tail_may_still_change(self):
        stab = PartialStabilizer()
        stab.update(words("the quick bro"))
        shown = stab.update(words("the quick brown"))
        self.assertEqual(texts(shown), ["the", "quick", "brown"])

    def test_punctuation_differences_still_agree(self):
        stab = PartialStabilizer()
        stab.update(words("well, then we go"))
        stab.update(words("well then we go on"))
        shown = stab.update(words("well then we go on now"))
        self.assertEqual(texts(shown), ["well", "then", "we", "go", "on", "now"])
        self.assertEqual(len(stab._locked), 5)

    def test_reset_forgets_locked_words(self):
        stab = PartialStabilizer()
        stab.update(words("a b c"))
        stab.update(words("a b c d"))
        stab.reset()
        self.assertEqual(texts(stab.update(words("x y"))), ["x", "y"])


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class CaptionBuilderTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.captions = CaptionBuilder(clock=self.clock)

    def test_words_accumulate_within_a_sentence(self):
        self.captions.add_final(words("this is"))
        self.captions.add_final(words("one sentence", start=1.0))
        self.assertEqual(texts(self.captions.visible()), ["this", "is", "one", "sentence"])

    def test_sentence_end_starts_new_caption(self):
        self.captions.add_final(words("It works."))
        restarted = self.captions.add_final(words("Next one", start=1.0))
        self.assertTrue(restarted)
        self.assertEqual(texts(self.captions.visible()), ["Next", "one"])

    def test_closing_quote_after_period_still_ends_sentence(self):
        self.captions.add_final([Word(text='go."', startTime=0.0, endTime=0.3)])
        self.assertTrue(self.captions.add_final(words("Then", start=0.5)))

    def test_long_pause_starts_new_caption(self):
        self.captions.add_final(words("hello there"))
        self.assertTrue(self.captions.add_final(words("again", start=5.0)))

    def test_caption_is_size_bounded(self):
        long_text = " ".join(["wordy"] * 30)
        self.captions.add_final(words(long_text, step=0.1))
        self.assertLessEqual(len(" ".join(texts(self.captions.visible()))), self.captions.max_chars)

    def test_caption_expires_after_hold_time(self):
        self.captions.add_final(words("hi"))
        self.clock.now += 1.0
        self.assertTrue(self.captions.visible())
        self.clock.now += 1.0
        self.assertEqual(self.captions.visible(), [])

    def test_longer_text_is_held_longer(self):
        self.captions.add_final(words(" ".join(["word"] * 12)))
        self.clock.now += 2.0
        self.assertTrue(self.captions.visible())

    def test_partial_shown_but_not_committed(self):
        self.captions.add_final(words("so we"))
        self.captions.set_partial(words("go now", start=1.0))
        self.assertEqual(texts(self.captions.visible()), ["so", "we", "go", "now"])
        self.assertEqual(self.captions.committed_text(), "so we")

    def test_final_supersedes_partial(self):
        self.captions.set_partial(words("gues text"))
        self.captions.add_final(words("guess text"))
        self.assertEqual(texts(self.captions.visible()), ["guess", "text"])

    def test_partial_starting_new_sentence_marks_translation_stale(self):
        self.captions.add_final(words("Done."))
        self.assertTrue(self.captions.shows_committed_caption)
        self.captions.set_partial(words("Now the", start=1.0))
        self.assertFalse(self.captions.shows_committed_caption)
        self.assertEqual(texts(self.captions.visible()), ["Now", "the"])

    def test_clear_empties_everything(self):
        self.captions.add_final(words("hi"))
        self.captions.clear()
        self.assertEqual(self.captions.visible(), [])
        self.assertEqual(self.captions.committed_text(), "")


if __name__ == "__main__":
    unittest.main()
