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
    from services.cache_service import CacheService
    cached_simple, _ = CacheService.get().get_definition(word, source_lang)
    if cached_simple is not None:
        return cached_simple

    try:
        definition, grammar = _lookup_simple(word, source_lang)
        result = {
            "word": word,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "definition": definition,
            "grammar": grammar,
            "error": None,
        }
        CacheService.get().save_simple(word, source_lang, result)
        return result
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
    from services.cache_service import CacheService
    _, cached_detail = CacheService.get().get_definition(word, source_lang)
    if cached_detail is not None:
        return cached_detail

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

        result = {
            "word": word,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "details": entry,
            "error": None,
        }
        CacheService.get().save_detail(word, source_lang, result)
        return result
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


# ── filtering / picking helpers (used by views + Anki export) ────────

SKIP_TAGS = {"not-comparable", "uncountable", "obsolete"}

BAD_FORM_TAGS = {
    "archaic", "obsolete", "dated", "rare", "dialect", "poetic", "nonstandard"
}

GOOD_FORM_TAGS = {
    "plural", "singular",
    "past", "past participle", "present participle", "gerund",
    "comparative", "superlative",
    "feminine", "masculine",
}


def pick_pronunciations(prons: list[dict], lang: str) -> list[dict]:
    if not prons:
        return []

    def tag_text(p):
        return " ".join(p.get("tags", [])).lower()

    if lang == "en":
        preferred = [p for p in prons if ("us" in tag_text(p) or "american" in tag_text(p))]
        return preferred or prons[:1]

    if lang == "pt":
        preferred = [p for p in prons if ("brazil" in tag_text(p) or "br" in tag_text(p))]
        return preferred or prons[:1]

    return prons[:1]


def pick_forms(forms: list[dict], limit: int = 8) -> list[dict]:
    if not forms:
        return []

    picked = []
    for f in forms:
        tags = set(t.lower() for t in f.get("tags", []))
        if tags & BAD_FORM_TAGS:
            continue
        if tags & GOOD_FORM_TAGS:
            picked.append(f)

    if not picked:
        for f in forms:
            tags = set(t.lower() for t in f.get("tags", []))
            if not (tags & BAD_FORM_TAGS):
                picked.append(f)
            if len(picked) >= 6:
                break

    return picked[:limit]


def is_inflection_definition(definition: str) -> bool:
    d = (definition or "").lower().strip()
    return (
        d.startswith("inflection of ")
        or " plural of " in d
        or d.startswith("plural of ")
        or " singular of " in d
        or d.startswith("singular of ")
    )


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