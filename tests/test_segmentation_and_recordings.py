import os
import sys
import tempfile
import types
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "App"))
sys.modules.setdefault("pyaudiowpatch", types.ModuleType("pyaudiowpatch"))

from models.config import TranscriptionConfig
from models.word import Word
from services.recording_store import RecordingStore
from services.segment_splitter import SegmentSplitter


def w(text, start, end):
    return Word(text=text, startTime=start, endTime=end)


class SegmentSplitterTests(unittest.TestCase):
    def test_prefers_the_real_pause_over_the_latest_word(self):
        words = [w("a", 0.0, 0.5), w("b", 0.6, 1.1), w("c", 1.2, 1.7),
                 w("d", 2.4, 2.9),          # 0.7 s pause before "d"
                 w("e", 3.0, 3.5), w("f", 3.6, 4.1)]
        self.assertEqual(SegmentSplitter.split_index(words, stable_end=4.1), 3)

    def test_prefers_sentence_end_when_there_is_no_pause(self):
        words = [w("one", 0.0, 1.0), w("two", 1.0, 2.0), w("three.", 2.0, 3.0),
                 w("four", 3.0, 4.0), w("five", 4.0, 5.0)]
        self.assertEqual(SegmentSplitter.split_index(words, stable_end=5.0), 3)

    def test_clause_comma_beats_plain_boundary(self):
        words = [w("so", 0.0, 1.0), w("then", 1.0, 2.0), w("again,", 2.0, 3.0),
                 w("we", 3.0, 4.0), w("go", 4.0, 5.0)]
        self.assertEqual(SegmentSplitter.split_index(words, stable_end=5.0), 3)

    def test_ties_choose_latest_boundary(self):
        words = [w(t, i * 0.5, i * 0.5 + 0.5) for i, t in enumerate("a b c d e f".split())]
        self.assertEqual(SegmentSplitter.split_index(words, stable_end=3.0), 6)

    def test_unstable_tail_is_never_finalized(self):
        words = [w("a", 0.0, 1.0), w("b", 1.0, 2.0), w("c", 2.0, 3.0), w("d", 3.0, 4.0)]
        self.assertEqual(SegmentSplitter.split_index(words, stable_end=3.0), 3)

    def test_no_tiny_fragments(self):
        words = [w("hi.", 0.0, 0.4), w("there", 0.4, 0.8)]
        self.assertIsNone(SegmentSplitter.split_index(words, stable_end=0.8))

    def test_empty(self):
        self.assertIsNone(SegmentSplitter.split_index([], stable_end=5.0))


class RecordingStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RecordingStore(os.path.join(self.tmp.name, "recordings"))
        self.config = TranscriptionConfig(model_size="small", language="pt", use_gpu=True)
        self.now = datetime(2026, 10, 25, 21, 31)

    def tearDown(self):
        self.tmp.cleanup()

    def test_name_contains_id_time_and_settings(self):
        path = self.store.new_session_path(self.config, self.now)
        self.assertEqual(os.path.basename(path), "0001_2026-10-25_2131_small_pt_gpu.wav")

    def test_cpu_is_reflected(self):
        self.config.use_gpu = False
        path = self.store.new_session_path(self.config, self.now)
        self.assertTrue(path.endswith("_small_pt_cpu.wav"))

    def test_ids_increment_over_existing_files(self):
        first = self.store.new_session_path(self.config, self.now)
        open(first, "wb").close()
        second = self.store.new_session_path(self.config, self.now)
        self.assertTrue(os.path.basename(second).startswith("0002_"))

    def test_id_continues_after_gaps_and_other_extensions(self):
        os.makedirs(self.store.directory)
        for name in ("0007_old_small_en_cpu.wav", "0007_old_small_en_cpu.txt", "notes.md"):
            open(os.path.join(self.store.directory, name), "w").close()
        path = self.store.new_session_path(self.config, self.now)
        self.assertTrue(os.path.basename(path).startswith("0008_"))

    def test_transcript_goes_next_to_the_wav(self):
        path = self.store.new_session_path(self.config, self.now)
        self.store.write_transcript(path, ["# header", "[ 1.00 - 2.00] hello"])
        with open(self.store.transcript_path(path), encoding="utf-8") as f:
            self.assertEqual(f.read(), "# header\n[ 1.00 - 2.00] hello\n")


if __name__ == "__main__":
    unittest.main()
