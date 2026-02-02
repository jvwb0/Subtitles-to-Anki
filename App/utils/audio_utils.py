import numpy as np
import wave
from models.word import Word

#audio prep + turning Whisper output into list[Word].

def prepareAudioFromWav(filename: str) -> np.ndarray:
    data, srcRate, channels = loadWav(filename)
    audio = bytesToNumpyArray(data, channels)
    audio = resampleAudio(audio, srcRate)
    return audio

def bytesToNumpyArray(data: bytes, channels: int) -> np.ndarray:
    audio = np.frombuffer(data, dtype=np.int16)

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)  # stereo → mono

    return audio.astype(np.float32) / 32768.0
     

def loadWav(filename: str) -> tuple[bytes, int, int]:
    with wave.open(filename, "rb") as wf:
        data = wf.readframes(wf.getnframes())
        return data, wf.getframerate(), wf.getnchannels()

    
def transcribeAudio(model, audio: np.ndarray, language: str = "en") ->  list[Word]:
    segments, info = model.transcribe(
        audio,
        language=language,      # ✅ force language (prevents random flips)
        task="transcribe",      # ✅ do NOT translate; just transcribe in that language
        beam_size=5,        # small beam for decent accuracy
        best_of=2,          # keep single pass for speed
        vad_filter=True,    # skip silence = faster + better results
        word_timestamps=True,
        condition_on_previous_text=False,   # reduces repetition
        no_speech_threshold=0.6,  # more aggressive speech detection
        )
    
    vocabulary: list[Word] = []

    for segment in segments:
        if not segment.words:
            continue
        for w in segment.words:
            vocabulary.append(Word(w.word.strip(), float(w.start), float(w.end)))

    return vocabulary
    
def resampleAudio(audio: np.ndarray, srcRate: int) -> np.ndarray:
    if srcRate == 16000:
        return audio

    xOld = np.linspace(0, len(audio) / srcRate, num=len(audio), endpoint=False)
    nNew = int(len(audio) * 16000 / srcRate)
    xNew = np.linspace(0, len(audio) / srcRate, num=nNew, endpoint=False)

    return np.interp(xNew, xOld, audio).astype(np.float32)
