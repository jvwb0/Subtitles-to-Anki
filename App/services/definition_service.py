import requests
import re
from urllib.parse import quote

BASE_URL = "https://freedictionaryapi.com/api/v1"

LANG_NAMES = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
}

# ── punctuation chars stripped from words before lookup ──────────────
_PUNCT = ".,!?;:\"'()[]{}"


# ── public API ───────────────────────────────────────────────────────

def fetch_definition(word: str, source_lang: str, target_lang: str) -> dict:
    """Hover card: first definition + part of speech only."""
    try:
        definition, grammar = _lookup_simple(word, source_lang)
        return {
            "word": word,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "definition": definition,
            "grammar": grammar,
            "error": None,
        }
    except Exception as e:
        return {
            "word": word,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "definition": "",
            "grammar": "",
            "error": str(e),
        }


def fetch_details(word: str, source_lang: str, target_lang: str) -> dict:
    """Click card: full entry — every sense, forms, pronunciations, syn/ant."""
    try:
        word_clean = word.strip(_PUNCT)
        entry = _get_entry(source_lang, word_clean)

        # If the first sense is just an inflection pointer, follow it so the
        # details card actually shows useful content.
        senses = entry.get("senses", [])
        if senses:
            base = _parse_inflection_base(senses[0].get("definition", ""))
            if base:
                try:
                    base_entry = _get_entry(source_lang, base)
                    note = {"definition": f'inflection of "{base}"', "tags": ["inflection"]}
                    entry["senses"] = [note] + base_entry.get("senses", [])
                    if not entry.get("forms"):
                        entry["forms"] = base_entry.get("forms", [])
                    if not entry.get("pronunciations"):
                        entry["pronunciations"] = base_entry.get("pronunciations", [])
                except Exception:
                    pass  # fall back to whatever we already have

        return {
            "word": word,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "details": entry,
            "error": None,
        }
    except Exception as e:
        return {
            "word": word,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "details": {},
            "error": str(e),
        }


# ── internal helpers ─────────────────────────────────────────────────

def _lookup_simple(word: str, lang: str) -> tuple[str, str]:
    word_clean = word.strip(_PUNCT)   # NO .lower() — preserve original case

    entry   = _get_entry(lang, word_clean)
    grammar = entry.get("partOfSpeech", "")
    senses  = entry.get("senses", [])
    if not senses:
        return "No definition found.", grammar

    definition = senses[0].get("definition", "No definition found.").strip()

    # If it's an inflection, follow the base word
    base = _parse_inflection_base(definition)
    if base:
        try:
            base_entry   = _get_entry(lang, base)
            base_grammar = base_entry.get("partOfSpeech", "") or grammar
            base_senses  = base_entry.get("senses", [])
            if base_senses:
                base_def = base_senses[0].get("definition", "").strip()
                return f"{definition}\n\nMeaning ({base}): {base_def}", base_grammar
        except Exception:
            pass  # fall back to original

    return definition, grammar


def _get_entry(lang: str, word_clean: str) -> dict:
    url = f"{BASE_URL}/entries/{lang}/{quote(word_clean)}"
    r = requests.get(url, timeout=6)

    if r.status_code == 404:
        # retry lower-cased
        r = requests.get(f"{BASE_URL}/entries/{lang}/{quote(word_clean.lower())}", timeout=6)
        if r.status_code == 404:
            raise Exception("Word not found")

    r.raise_for_status()
    return r.json()["entries"][0]


def _parse_inflection_base(definition: str) -> str | None:
    """
    Extract the base word from inflection-style definitions like
    "plural of Haus", "masculine plural of Hund", etc.
    """
    m = re.search(r"\bof\s+(.+)$", definition.strip(), re.IGNORECASE)
    if not m:
        return None

    base = m.group(1).strip().strip(_PUNCT)
    # take first token only (avoids grabbing trailing API notes)
    base = base.split()[0] if base else ""
    return base or None