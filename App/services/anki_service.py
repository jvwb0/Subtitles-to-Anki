"""
AnkiConnect integration — adds flashcards to a running Anki instance.

Requires Anki with the AnkiConnect plugin (localhost:8765).
Auto-launches Anki if not already running.
"""

import os
import glob
import subprocess
import time
import requests

from interfaces.anki_gateway import IAnkiGateway
from services.anki_note_template import AnkiNoteTemplate

ANKI_URL = "http://localhost:8765"
ANKI_VERSION = 6

_ANKI_SEARCH_DIRS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Anki"),
    r"C:\Program Files\Anki",
    r"C:\Program Files (x86)\Anki",
]


def _invoke(action: str, **params) -> dict:
    payload = {"action": action, "version": ANKI_VERSION}
    if params:
        payload["params"] = params
    r = requests.post(ANKI_URL, json=payload, timeout=4)
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise Exception(body["error"])
    return body


def is_anki_available() -> bool:
    try:
        _invoke("version")
        return True
    except Exception:
        return False


def _find_anki_exe() -> str | None:
    for directory in _ANKI_SEARCH_DIRS:
        pattern = os.path.join(directory, "anki.exe")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None


def ensure_anki_running(timeout: float = 15.0) -> bool:
    """Launch Anki if not running. Wait up to `timeout` seconds for AnkiConnect.
    Returns True if AnkiConnect is reachable afterwards."""
    if is_anki_available():
        return True

    exe = _find_anki_exe()
    if not exe:
        return False

    subprocess.Popen([exe], creationflags=subprocess.DETACHED_PROCESS)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_anki_available():
            return True
        time.sleep(1.0)

    return False


def get_deck_names() -> list[str]:
    body = _invoke("deckNames")
    return body.get("result", [])


def create_deck(deck_name: str) -> dict:
    try:
        _invoke("createDeck", deck=deck_name)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


_model_checked = False


def ensure_model_exists():
    """Create the custom note type if it doesn't already exist (cached after first check)."""
    global _model_checked
    if _model_checked:
        return
    body = _invoke("modelNames")
    if AnkiNoteTemplate.MODEL_NAME in body.get("result", []):
        _model_checked = True
        return
    _invoke(
        "createModel",
        modelName=AnkiNoteTemplate.MODEL_NAME,
        inOrderFields=AnkiNoteTemplate.FIELDS,
        css=AnkiNoteTemplate.CSS,
        cardTemplates=[{
            "Name": "Card 1",
            "Front": AnkiNoteTemplate.FRONT,
            "Back": AnkiNoteTemplate.BACK,
        }],
    )
    _model_checked = True


def add_note(deck_name: str, fields: dict) -> dict:
    try:
        ensure_model_exists()
        _invoke(
            "addNote",
            note={
                "deckName": deck_name,
                "modelName": AnkiNoteTemplate.MODEL_NAME,
                "fields": fields,
                "options": {
                    "allowDuplicate": False,
                    "duplicateScope": "deck",
                },
            },
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def build_note_fields(
    word_text: str,
    simple_result: dict,
    detail_result: dict,
    src_lang: str,
) -> dict:
    """Build the field dict for a 'Subtitles to Anki' note from API results."""
    from services.definition_service import (
        SKIP_TAGS, pick_pronunciations, pick_forms, is_inflection_definition,
    )

    d = detail_result.get("details", {})

    # Meaning
    meaning_parts = []
    simple_def = simple_result.get("definition", "")
    if simple_def and simple_def != "No definition found.":
        meaning_parts.append(simple_def)

    senses = d.get("senses", [])
    if senses:
        filtered = [s for s in senses if not (set(s.get("tags", [])) & SKIP_TAGS)]
        real = [s for s in filtered if not is_inflection_definition(s.get("definition", ""))]
        infl = [s for s in filtered if is_inflection_definition(s.get("definition", ""))]
        for s in (real or infl)[:3]:
            defi = s.get("definition", "")
            if defi and defi != simple_def:
                meaning_parts.append(defi)

    # Grammar
    grammar_parts = []
    pos = d.get("partOfSpeech", simple_result.get("grammar", ""))
    if pos:
        grammar_parts.append(pos)
    prons = pick_pronunciations(d.get("pronunciations", []), src_lang)
    if prons:
        pron_text = prons[0].get("text", "")
        if pron_text:
            grammar_parts.append(pron_text)
    forms = pick_forms(d.get("forms", []))
    if forms:
        form_strs = []
        for f in forms[:4]:
            w = f.get("word", "")
            tags = f.get("tags", [])
            tag_str = f" ({', '.join(tags)})" if tags else ""
            form_strs.append(f"{w}{tag_str}")
        grammar_parts.append("Forms: " + ", ".join(form_strs))

    # Example
    example = ""
    if senses:
        for s in senses:
            examples = s.get("examples", [])
            if examples:
                example = examples[0]
                break

    return {
        "Word": word_text,
        "Meaning": " | ".join(meaning_parts) if meaning_parts else "",
        "Grammar": " · ".join(grammar_parts) if grammar_parts else "",
        "Example": example,
        "Example Translation": "",
        "Register": pos if pos else "",
    }


class AnkiService(IAnkiGateway):
    """Thin OOP facade over the AnkiConnect functions above."""

    # ── connection lifecycle ──────────────────────────────────────────
    def is_available(self) -> bool:
        return is_anki_available()

    def ensure_running(self, timeout: float = 15.0) -> bool:
        return ensure_anki_running(timeout)

    # ── deck CRUD ──────────────────────────────────────────────────────
    def get_deck_names(self) -> list[str]:
        return get_deck_names()

    def create_deck(self, deck_name: str) -> dict:
        return create_deck(deck_name)

    # ── note CRUD ────────────────────────────────────────────────────
    def add_note(self, deck_name: str, fields: dict) -> dict:
        return add_note(deck_name, fields)
