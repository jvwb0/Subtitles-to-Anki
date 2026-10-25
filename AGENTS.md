# AGENTS.md — Subtitles-to-Anki

Briefing for AI coding agents. Read this before changing anything. Keep it updated when goals, architecture, or conventions change.

Full background, data structures, data flow, tuning constants and the known-bug list live in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

## 1. What this project is

A Windows desktop app that captures system audio (WASAPI loopback), transcribes it live with Whisper, and shows clickable subtitles in an always-on-top overlay. Hovering a word shows a quick definition; clicking opens full details and can export a flashcard to Anki (via AnkiConnect). An optional second line shows an English translation.

Intended use: watching foreign-language video (e.g. a full Netflix film) and learning vocabulary without leaving the video.

## 2. Owner's goals (priority order)

1. **Clean MVC + OOP architecture.** Interfaces, clear structure, getters/setters grouped together, CRUD grouped together, declarations at the top, no copy-pasted logic, no clever shortcuts, styling in one stylesheet, objects modeled as classes. A new contributor must be able to tell what to debug without help.
2. **Lightweight, easy setup for GitHub users.** Do not require heavy downloads. RAM and disk are valuable. Dependencies must be pinned and documented so strangers can run the project.
3. **Runs efficiently for a whole film.** The app must not overheat the machine or build up lag/stutter over hours. Be selective and specific with resources.
4. **Modern, friendly GUI.** The original Tkinter UI was rejected as ugly and old. Target: Windows 11 look, follows system light/dark, vibrant blue accent, new users should not be intimidated.
5. **Debuggability.** The project will keep growing for months. Logging and error handling are a first-class concern.
#
## 2b. Product vision and linguistic principle (owner, 2026-10-25)

Quality bar: **YouTube auto-captions or better** - fast, punctuated, paced with the speaker, never an endless run-on sentence. A light, no-hassle app that runs carefree beside a film. GPU preferred, must degrade gracefully to CPU.

**Interpret, do not translate.** The user is an English speaker learning e.g. Portuguese/Spanish and wants to understand the language the way natives do.
- The English caption line must be a meaning-faithful translation of the *whole finished sentence*, using the previous 1-2 sentences as context. Never word by word. Do not use Whisper's `translate` task for it. Google Translate is a stopgap, not the target (planned: local CTranslate2 model such as Opus-MT/NLLB; an optional small local LLM for idioms/register, off the live critical path).
- The hover card is a **context-aware bilingual learner entry (target word -> English)**, not a target-language dictionary: the sense that applies *in this sentence* first (e.g. *ficar* = stay / become / be located), lemma + conjugation (*fui* -> *ser/ir*, preterite 1sg), part of speech, gender, register, one short example; multi-word units/idioms (*dar certo*) as one item. Today it still shows `senses[0]` from an online dictionary; replacing it is planned (offline Wiktionary-derived data + sentence-aware sense selection).
- Anki: the owner has a very specific card layout and will share it **only after** the engineering is solid. Do not invent a template; keep the exporter's field mapping abstract.

## 3. Status (as of 2026-10-25)

Done:
- Torch/torchaudio/torchvision removed. Silero VAD now runs on ONNX Runtime. GPU for Whisper comes from `ctranslate2` directly.
- Controller split into focused sub-controllers behind an `AppController` facade; service interfaces in `App/interfaces/`.
- GUI rewritten from Tkinter to PySide6 with a central QSS theme (`views/theme.py`), Fusion style, Windows 11 Mica backdrop.
- Logging system with rotating file, global exception hooks, Qt message forwarding, and `faulthandler`.
- Transcript text box capped (it previously grew unbounded and slowed the UI over long sessions).
- **5-minute stall fixed (2026-10-25).** `AudioCaptureLive` now uses a locked `deque(maxlen)` plus a monotonic `total_chunks`; consumers use `chunks_since(cursor)` and `elapsed_sec` instead of `len(frames)`. Covered by `tests/test_vad_pipeline.py`.
- **Live partial captions in VAD mode (2026-10-25).** Measured by replaying a real 57 s recording (small model, CUDA) with `tools/replay_wav.py`: delay between a word ending and appearing on screen fell from **2.27 s mean / 3.55 s p90 to 0.79 s mean / 1.38 s p90**. Whisper itself takes only 0.2-0.3 s per 2-4 s of audio, so the old delay was batching (nothing shown until a pause or the 4 s cap), not inference. `VadTranscriber.tick()` now returns `(final_words, partial_words)`: `partial_words` is `None` for "no change", a list of live words while speech continues, and `[]` when a final result supersedes it. `MainWindow` shows `final buffer + partial` and skips overlay rebuilds when the partial text is unchanged.
- **Sentence-paced captions, stable partials, guards (2026-10-25).** `services/caption_builder.py` replaces the rolling 10-word window: captions are one sentence / max 2x42 chars, split on sentence end or a >1.2 s gap, held max(1.5 s, 0.05 s/char); live partial words are shown on top of committed finals (never committed). `MainWindow` refreshes via a 100 ms `QTimer` (expiry) and only rebuilds the overlay when the visible text changed. The English line translates only committed caption text and is cleared when the caption changes; late translations are dropped. `services/partial_stabilizer.py` locks words two consecutive hypotheses agree on (newest word never locked): replay flicker 18.7 -> 11.8 reworded words/100 shown for ~+0.2 s mean delay (`VadTranscriber(stabilize_partials=...)`). `WhisperService` drops likely hallucinated segments (no_speech+low logprob, compression ratio > 2.4, Amara-style credits) and collapses >3 identical word repeats. `VadTranscriber` feeds the last ~150 chars of final text to Whisper as `initial_prompt` (`ITranscriptionEngine.transcribe(..., prompt=)`); on the test clip it fixed garbled sentences and hyphen artefacts (single clip, single run - re-check on more audio).
- Automated tests exist: `python -m unittest discover -s tests` (recorder buffer/cursor, VAD partial/final flow, stabilizer, caption builder, Whisper guards).
- `tools/replay_wav.py`: replays a WAV through the real VAD+Whisper pipeline in real time and prints on-screen delay. Run it with the project `.venv` (it has the CUDA libraries): `.venv\Scripts\python.exe tools\replay_wav.py file.wav --model small --lang en`.

Not done / unverified (do not claim these are solved):
- Partial text still flickers a little in the unstable tail, and a forced 4 s flush can still cut a sentence (split at the quietest point is planned). Hallucination guards and the context prompt were only checked on one clip; the prompt can also let a wrong word propagate - watch for it.
- Real-audio quality has only been checked on one 57 s mixed English/Portuguese clip; no WER measurement, no long-session soak, and the live GUI was not run by the agent that made the partial-caption change (only the window logic was exercised headless; the new CaptionBuilder wiring has not been seen live either).
- **Unexplained crash.** The app once exited with code 1 and no Python traceback, so it was probably a native-level fault. Cause is unconfirmed. `faulthandler` was added; if it recurs, read `logs/faulthandler.log` first, then `logs/app.log`.
- **Long-session heat/lag has not been measured** on a real full-length film. The only changes made are the transcript cap and recommending VAD mode. Fast/Accurate modes re-run Whisper on a sliding window every 0.3–0.7 s regardless of speech, which is inherently heavy.
- Visual polish of the new GUI has only been partly reviewed by the owner (see backlog).
- `README.md` and `VAD_INTEGRATION.md` are outdated (they describe the early prototype and the torch-based VAD). Setup instructions for GitHub users still need to be written.
- `.claude/` and loose files in the repo root (`live.wav`, a personal `.wav`, `word_cache.db*`) have not been reviewed; do not delete them without asking.

Backlog (low priority, owner called these nit-picky): user-adjustable subtitle font size, optional drop shadow, opacity slider, independent controls for the translation line, and a re-check of hover-card formatting. Also saved in `/memories/repo/gui_backlog.md`.

## 4. Architecture

```
App/
  main.py                 entry point: logging, QApplication, Fusion style, theme, MainWindow
  models/                 plain data: Word, TranscriptionConfig, reference_data (languages, model info)
  interfaces/             ABCs: ITranscriptionEngine, IAudioRecorder, IVoiceActivityDetector,
                          IAnkiGateway, IDefinitionProvider, ITranslationProvider, ICacheRepository
  services/               implementations (talk to the outside world)
  controllers/            orchestration; threads live here
  views/                  PySide6 UI only
  utils/                  app_logger, text_utils
```

Layering rules:
- Views call `AppController` only. They never import services for behavior (display helpers like `pick_forms` are the one tolerated exception).
- `AppController` is a facade over `TranscriptionController`, `DefinitionController`, `AnkiController`, `TranslationController`. Keep its public API stable; add new features to the matching sub-controller.
- Controllers depend on interfaces, services implement them.
- Models contain no I/O or Qt.

Key services:
- `whisper_service.py` — faster-whisper; device chosen from `use_gpu` (True/False/None=auto via `ctranslate2.get_cuda_device_count()`).
- `vad_service.py` — Silero VAD via ONNX Runtime; model auto-downloaded to `~/.cache/silero_vad/` on first run.
- `audio_capture_live.py` — WASAPI loopback capture, ring buffer capped at 5 minutes. Methods are snake_case (`read_chunk`, `get_recent_chunks`).
- `live_transcriber.py` (Fast/Accurate sliding-window mode with provisional/confirmed words) and `vad_transcriber.py` (transcribe only on speech pauses; lowest resource use, default).
- `definition_service.py` (freedictionaryapi.com), `translation_service.py` (Google via deep-translator, debounced), `cache_service.py` (SQLite `word_cache.db` at repo root), `anki_service.py` + `anki_note_template.py` (AnkiConnect at localhost:8765, card HTML/CSS).

Threading model:
- Audio capture thread and transcription thread are started by `TranscriptionController`.
- Background threads must never touch widgets. They emit Qt `Signal`s; slots run on the GUI thread. Follow this pattern for every new callback.

## 5. Conventions

- Style: declarations/constants at the top of a class, then public API, then private helpers; group getters/setters and CRUD methods together; snake_case everywhere; one-line comments only when the code cannot explain itself.
- No duplicated logic. Extract a helper (example: `shift_timestamps` in `models/word.py`).
- Styling lives in `views/theme.py`. Do not hard-code colors or fonts in views.
- **Qt gotchas learned the hard way:**
  - The app uses `setStyle("Fusion")`; the native Windows style ignores most QSS (buttons looked unclickable).
  - App-level QSS `font-size` overrides `setFont()`. Use `Theme.font_css(spec)` inside the widget's own stylesheet.
  - Never set `background` on the blanket `QWidget` selector; it paints opaque boxes behind nested labels.
  - QSS does not support 8-digit hex colors; use `Theme.rgba(hex, alpha)`.
- Logging: use `get_logger(__name__)`, never `print()`. Wrap background-thread bodies and slots that render external data in try/except with `logger.exception(...)`.
- ctypes/WinAPI calls must declare `argtypes`/`restype` and check return codes.
- Do not add heavyweight dependencies without asking (see goal 2). Do not reintroduce torch.
- Do not create extra markdown files unless asked.

## 6. How to run

Use the project venv (`.venv`, Python 3.12). All imports are relative to `App/`, so run from there:

```powershell
cd App
..\.venv\Scripts\python.exe main.py
```

Install: `pip install -r requirements.txt` (pinned; PySide6 6.11.2, faster-whisper 1.2.1, ctranslate2 4.6.3, onnxruntime 1.23.2, PyAudioWPatch). GPU use needs an NVIDIA driver and CUDA runtime libraries; otherwise it falls back to CPU.

Debugging artifacts (git-ignored):
- `logs/app.log` — rotating app log, includes uncaught exceptions and Qt warnings.
- `logs/faulthandler.log` — native crash stacks.

## 7. Working agreement with the owner

- Large or destructive changes (deleting files, renaming modules, new heavy dependencies) should be confirmed first. Small reversible edits can proceed.
- Verify before claiming success: run `get_errors`, a smoke script, or the app. Say plainly what was and was not verified.
- The owner reviews the GUI visually and gives specific feedback; act on it directly and re-launch the app afterward.
- Take time on GUI work; the owner explicitly asked not to rush it.
