# services/definition_service.py
"""
Looks up definition + grammar info for a single word.

    fetch_definition(word, source_lang, target_lang) -> dict

    source_lang  – the language the word was transcribed in   (e.g. "de")
    target_lang  – the language the user wants the answer in  (e.g. "en")

Returns:
    {
        "word":         str,    # the word as looked up
        "source_lang":  str,    # e.g. "de"
        "target_lang":  str,    # e.g. "en"
        "definition":   str,    # plain-text definition
        "grammar":      str,    # part-of-speech, declension, notes …
        "error":        str|None
    }

STUB — replace _lookup() with a real API / LLM call when ready.
"""

import time                          # only here so the stub can simulate latency


# Human-readable language name map (code → name) — used in the card header
LANG_NAMES: dict[str, str] = {
    "en": "English", "de": "German", "fr": "French", "pt": "Portuguese",
    "es": "Spanish", "it": "Italian", "nl": "Dutch", "pl": "Polish",
    "tr": "Turkish", "ru": "Russian", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese",
}


def fetch_definition(word: str, source_lang: str, target_lang: str) -> dict:
    """
    Public entry-point.  Always returns the full dict — never raises.
    """
    try:
        definition, grammar = _lookup(word, source_lang, target_lang)
        return {
            "word":        word,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "definition":  definition,
            "grammar":     grammar,
            "error":       None,
        }
    except Exception as e:
        return {
            "word":        word,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "definition":  "",
            "grammar":     "",
            "error":       str(e),
        }


# ──────────────────────────────────────────────────────────────────────
# STUB  ← replace this function body with your real backend
# ──────────────────────────────────────────────────────────────────────
def _lookup(word: str, source_lang: str, target_lang: str) -> tuple[str, str]:
    """
    Returns (definition, grammar_info) as plain strings.

    TODO: swap in one of:
        • Anthropic API  – prompt Claude with the word + languages
        • Dictionaryapi.dev (free, no key)
        • DeepL or Google Translate API
        • wiktionary API
    """
    # Simulate network latency so the "Loading…" state is visible during dev
    time.sleep(0.6)

    src_name = LANG_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_NAMES.get(target_lang, target_lang)

    # Placeholder text — obvious during testing
    definition = f"[STUB] {tgt_name} definition of \"{word}\" (from {src_name}) goes here."
    grammar    = f"[STUB] Part of speech, declension, usage notes in {tgt_name} go here."

    return definition, grammar