"""
Replay a WAV through the real VAD + Whisper pipeline in real time and report
caption latency (how long after a word was spoken it is emitted).

Usage (from repo root):
    python tools\replay_wav.py path\to\file.wav [--model small] [--cpu] [--lang en] [--max-sec 60]
        [--no-stabilize] [--no-prompt] [--max-speech SEC]
"""

import argparse
import os
import statistics
import sys
import threading
import time
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "App"))

from services.audio_capture_live import AudioCaptureLive
from services.vad_service import VadService
from services.vad_transcriber import VadTranscriber
from services.whisper_service import WhisperService


def feed(recorder, wav_path, max_sec, t0, done):
    """Append audio chunks to the recorder at real-time pace."""
    with wave.open(wav_path, "rb") as wf:
        chunk = recorder.chunk
        total = int(max_sec * wf.getframerate() / chunk) if max_sec else None
        i = 0
        while total is None or i < total:
            data = wf.readframes(chunk)
            if len(data) < chunk * wf.getsampwidth() * wf.getnchannels():
                break
            due = t0 + (i + 1) * chunk / wf.getframerate()
            time.sleep(max(0.0, due - time.monotonic()))
            recorder.append_chunk(data)
            i += 1
    done.set()


def percentile(values, pct):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * pct / 100))]


def segment_texts(finals):
    """Final words grouped by the tick that emitted them."""
    batch, last_wall = [], None
    for wall, w in finals:
        if last_wall is not None and abs(wall - last_wall) > 1e-6:
            yield " ".join(batch)
            batch = []
        batch.append(w.text)
        last_wall = wall
    if batch:
        yield " ".join(batch)


def flicker_per_100(partials, final_walls):
    """Words already on screen (all but the newest) that a later update rewrote."""
    def key(w):
        return "".join(c for c in w.text.lower() if c.isalnum())

    changed = shown = 0
    for (wall_a, a), (wall_b, b) in zip(partials, partials[1:]):
        if any(wall_a < f <= wall_b for f in final_walls):
            continue  # a final text in between legitimately resets the segment
        stable = [key(w) for w in a[:-1]]
        same = 0
        for x, y in zip(stable, [key(w) for w in b]):
            if x != y:
                break
            same += 1
        changed += len(stable) - same
        shown += len(b)
    return 100.0 * changed / shown if shown else 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wav")
    parser.add_argument("--model", default="small")
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--max-sec", type=float, default=0)
    parser.add_argument("--no-stabilize", action="store_true", help="show raw partial hypotheses")
    parser.add_argument("--no-prompt", action="store_true", help="don't feed previous text to Whisper")
    parser.add_argument("--max-speech", type=float, help="override VadTranscriber.MAX_SPEECH_SEC")
    args = parser.parse_args()
    if args.max_speech:
        VadTranscriber.MAX_SPEECH_SEC = args.max_speech

    with wave.open(args.wav, "rb") as wf:
        rate, channels = wf.getframerate(), wf.getnchannels()

    whisper = WhisperService(args.model, use_gpu=not args.cpu)
    vad = VadService()
    recorder = AudioCaptureLive(rate=rate, channels=channels)
    transcriber = VadTranscriber(whisper, recorder, vad, args.lang,
                                 stabilize_partials=not args.no_stabilize,
                                 use_context_prompt=not args.no_prompt)

    done = threading.Event()
    t0 = time.monotonic()
    threading.Thread(target=feed, args=(recorder, args.wav, args.max_sec, t0, done), daemon=True).start()

    finals = []    # (wall_seconds, word)
    partials = []  # (wall_seconds, [words])

    def pump():
        final, partial = transcriber.tick()
        now = time.monotonic() - t0
        finals.extend((now, w) for w in final)
        if partial:
            partials.append((now, partial))

    while not done.is_set():
        pump()
        time.sleep(0.05)
    for _ in range(40):  # let the final segment flush
        pump()
        time.sleep(0.05)

    if not finals:
        print("No words emitted.")
        return

    def key(w):
        return "".join(c for c in w.text.lower() if c.isalnum())

    def first_shown(final_wall, word):
        """Earliest wall time the word was visible, as a partial or as final text."""
        best = final_wall
        for wall, words in partials:
            if wall < best and any(key(w) == key(word) and abs(w.startTime - word.startTime) < 0.5 for w in words):
                best = wall
        return best

    def report(label, walls_words):
        lat = [wall - w.endTime for wall, w in walls_words]
        print(f"{label}: mean {statistics.mean(lat):.2f}s  p50 {percentile(lat, 50):.2f}s  "
              f"p90 {percentile(lat, 90):.2f}s  max {max(lat):.2f}s")

    print(f"\nfinal words: {len(finals)}   partial updates: {len(partials)}")
    print("delay between a word ENDING and it appearing on screen")
    report("  final text only (old behaviour)", finals)
    report("  with live partial text         ", [(first_shown(wall, w), w) for wall, w in finals])

    print(f"  flicker: {flicker_per_100(partials, [wall for wall, _ in finals]):.1f} "
          "reworded words per 100 shown")

    print(f"  segment ends: {dict(transcriber.cut_counts)}")
    texts = [t for t in segment_texts(finals)]
    ends_clean = sum(t.rstrip("\"')").endswith((".", "?", "!", ",", "?")) for t in texts)
    print(f"  segments ending on punctuation: {ends_clean}/{len(texts)}")

    print("\nfinal text by emission:")
    batch, last_wall = [], None
    for wall, w in finals:
        if last_wall is not None and abs(wall - last_wall) > 1e-6:
            print(f"  [{last_wall:6.2f}s] {' '.join(batch)}")
            batch = []
        batch.append(w.text)
        last_wall = wall
    if batch:
        print(f"  [{last_wall:6.2f}s] {' '.join(batch)}")
    print("\nsample partial updates:")
    for wall, words in partials[:12]:
        print(f"  [{wall:6.2f}s] {' '.join(w.text for w in words)}")


if __name__ == "__main__":
    main()
