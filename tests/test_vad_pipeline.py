import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "App"))
sys.modules.setdefault("pyaudiowpatch", types.ModuleType("pyaudiowpatch"))

import numpy as np

from models.word import Word
from services.audio_capture_live import AudioCaptureLive
from services.vad_transcriber import VadTranscriber

RATE = 16000
CHUNK = 512  # one VAD frame per chunk keeps the arithmetic obvious
FRAME_SEC = CHUNK / RATE


def make_recorder(max_seconds=None):
    rec = AudioCaptureLive(rate=RATE, channels=1, chunk=CHUNK)
    if max_seconds is not None:
        from collections import deque
        rec._max_chunks = int(max_seconds * RATE / CHUNK)
        rec._frames = deque(maxlen=rec._max_chunks)
    return rec


def chunk_bytes():
    return (np.ones(CHUNK, dtype=np.int16) * 1000).tobytes()


class FakeVad:
    """Speech probability driven by a script: a list of booleans, one per frame."""
    FRAME_SIZE = CHUNK
    SAMPLE_RATE = RATE

    def __init__(self):
        self.script = []
        self.i = 0

    def reset(self):
        self.i = 0

    def speech_prob(self, frame):
        speaking = self.script[self.i] if self.i < len(self.script) else False
        self.i += 1
        return 0.9 if speaking else 0.0


class FakeWhisper:
    """Returns one word per second of audio it is given, spanning the clip."""

    def __init__(self):
        self.calls = 0

    def transcribe(self, audio, language="en", task="transcribe"):
        self.calls += 1
        dur = len(audio) / RATE
        n = max(1, int(dur))
        step = dur / n
        return [Word(f"w{i}", i * step, (i + 1) * step) for i in range(n)]


class RecorderBufferTests(unittest.TestCase):
    def test_cursor_keeps_working_after_buffer_cap(self):
        rec = make_recorder(max_seconds=1)
        cursor, seen = 0, 0
        for _ in range(500):
            rec.append_chunk(chunk_bytes())
            chunks, cursor = rec.chunks_since(cursor)
            seen += len(chunks)
        self.assertEqual(seen, 500)
        self.assertEqual(len(rec.frames), rec._max_chunks)
        self.assertAlmostEqual(rec.elapsed_sec, 500 * FRAME_SEC)

    def test_stale_cursor_resumes_from_oldest_kept(self):
        rec = make_recorder(max_seconds=1)
        for _ in range(200):
            rec.append_chunk(chunk_bytes())
        chunks, cursor = rec.chunks_since(0)
        self.assertEqual(len(chunks), rec._max_chunks)
        self.assertEqual(cursor, 200)

    def test_nothing_new_returns_empty(self):
        rec = make_recorder()
        rec.append_chunk(chunk_bytes())
        _, cursor = rec.chunks_since(0)
        chunks, again = rec.chunks_since(cursor)
        self.assertEqual((chunks, again), ([], cursor))


class VadPartialTests(unittest.TestCase):
    def setUp(self):
        self.rec = make_recorder()
        self.vad = FakeVad()
        self.whisper = FakeWhisper()
        self.tr = VadTranscriber(self.whisper, self.rec, self.vad)

    def run_script(self, script):
        """Feed one frame per script entry; collect every tick result."""
        self.vad.script = script
        results = []
        for _ in script:
            self.rec.append_chunk(chunk_bytes())
            results.append(self.tr.tick())
        return results

    def test_partials_appear_while_speaking_then_final_clears_them(self):
        speech = int(2.0 / FRAME_SEC)   # 2 s of speech
        pause = int(0.5 / FRAME_SEC)    # enough silence to end the segment
        results = self.run_script([True] * speech + [False] * pause)

        partials = [p for _, p in results if p]
        finals = [(f, p) for f, p in results if f]
        self.assertGreaterEqual(len(partials), 2, "live partial text expected during speech")
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0][1], [], "final event must clear the partial text")

    def test_no_partial_before_minimum_speech(self):
        results = self.run_script([True] * int(0.3 / FRAME_SEC))
        self.assertTrue(all(p is None for _, p in results))

    def test_silence_reports_no_change(self):
        results = self.run_script([False] * 50)
        self.assertTrue(all(r == ([], None) for r in results))

    def test_partial_does_not_advance_final_emission_cursor(self):
        self.run_script([True] * int(1.5 / FRAME_SEC))
        self.assertEqual(self.tr._last_emitted_end, 0.0)

    def test_final_words_are_not_repeated_in_later_partials(self):
        speech = int(1.5 / FRAME_SEC)
        pause = int(0.5 / FRAME_SEC)
        first = self.run_script([True] * speech + [False] * pause)
        final_words = [w for f, _ in first for w in f]
        self.assertTrue(final_words)
        last_end = max(w.endTime for w in final_words)

        # second utterance: every partial word must start after what was already emitted
        self.vad.script = [True] * int(1.5 / FRAME_SEC)
        self.vad.i = 0
        later = []
        for _ in self.vad.script:
            self.rec.append_chunk(chunk_bytes())
            _, partial = self.tr.tick()
            later.extend(partial or [])
        self.assertTrue(all(w.endTime > last_end for w in later))

    def test_runs_past_the_buffer_cap(self):
        rec = make_recorder(max_seconds=2)
        tr = VadTranscriber(self.whisper, rec, self.vad)
        self.vad.i = 0
        self.vad.script = ([True] * 40 + [False] * 20) * 20  # ~25 s of speech/pause cycles
        finals = 0
        for _ in self.vad.script:
            rec.append_chunk(chunk_bytes())
            final, _ = tr.tick()
            finals += bool(final)
        self.assertGreaterEqual(finals, 15, "segments must keep being detected after the cap")


if __name__ == "__main__":
    unittest.main()
