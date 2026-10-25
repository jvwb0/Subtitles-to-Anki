# models/reference_data.py
"""Static reference data: supported languages and Whisper model tradeoffs."""

LANGUAGES = [
    ("English",    "en"),
    ("German",     "de"),
    ("French",     "fr"),
    ("Portuguese", "pt"),
    ("Spanish",    "es"),
    ("Italian",    "it"),
    ("Dutch",      "nl"),
    ("Polish",     "pl"),
    ("Turkish",    "tr"),
    ("Russian",    "ru"),
    ("Japanese",   "ja"),
    ("Korean",     "ko"),
    ("Chinese",    "zh"),
]

MODEL_INFO = {
    "tiny":     "Fastest, least accurate (~1 GB VRAM, ~150 MB RAM)",
    "base":     "Fast, decent accuracy (~1 GB VRAM, ~300 MB RAM)",
    "small":    "Balanced speed/accuracy (~2 GB VRAM, ~500 MB RAM)",
    "medium":   "Slower, high accuracy (~5 GB VRAM, ~1.5 GB RAM)",
    "large-v2": "Very slow, highest accuracy (~10 GB VRAM, ~3 GB RAM)",
    "large-v3": "Newest large model (~10 GB VRAM, ~3 GB RAM)",
    "turbo":    "Fast large model, good balance (~6 GB VRAM, ~1.5 GB RAM)",
}
