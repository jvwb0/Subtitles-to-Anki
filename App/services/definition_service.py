import requests

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

def fetch_definition(word: str, source_lang: str, target_lang: str) -> dict:
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

def _lookup_simple(word: str, lang: str) -> tuple[str, str]:
    word = word.strip(".,!?;:\"'()[]{}").lower()
    url = f"{BASE_URL}/entries/{lang}/{word}"

    r = requests.get(url, timeout=6)
    if r.status_code == 404:
        raise Exception("Word not found")
    r.raise_for_status()

    data = r.json()
    entry = data["entries"][0]

    grammar = entry.get("partOfSpeech", "")

    senses = entry.get("senses", [])
    if not senses:
        return "No definition found.", grammar

    definition = senses[0].get("definition", "No definition found.")
    return definition, grammar