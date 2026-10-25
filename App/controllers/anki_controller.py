# controllers/anki_controller.py
"""Anki deck/note CRUD, run in background threads for the GUI."""

import threading

from interfaces.anki_gateway import IAnkiGateway
from services.anki_service import build_note_fields
from utils.app_logger import get_logger

logger = get_logger(__name__)


class AnkiController:
    def __init__(self, anki_gateway: IAnkiGateway):
        self._anki = anki_gateway

    def ensure_anki_ready(self, on_ready):
        """Launch Anki + fetch deck list in a background thread.
        Calls on_ready(ok: bool, decks: list) on the BG thread."""
        def bg():
            try:
                ok = self._anki.ensure_running(timeout=15.0)
                decks = []
                if ok:
                    try:
                        decks = self._anki.get_deck_names()
                    except Exception:
                        logger.exception("get_deck_names failed")
                on_ready(ok, decks)
            except Exception:
                logger.exception("ensure_anki_ready failed")
                on_ready(False, [])
        threading.Thread(target=bg, daemon=True).start()

    # ── deck CRUD ──────────────────────────────────────────────────────
    def create_anki_deck(self, name, on_ready):
        """Create a new Anki deck in a background thread.
        Calls on_ready(result: dict) on the BG thread."""
        def bg():
            try:
                on_ready(self._anki.create_deck(name))
            except Exception as e:
                logger.exception("create_anki_deck failed for name=%r", name)
                on_ready({"success": False, "error": str(e)})
        threading.Thread(target=bg, daemon=True).start()

    # ── note CRUD ────────────────────────────────────────────────────
    def save_to_anki(self, word, deck_name, src_lang, on_ready):
        """Build note fields and save to Anki in a background thread.
        Calls on_ready(result: dict) on the BG thread."""
        def bg():
            try:
                fields = build_note_fields(
                    word.text, word.simple_result or {}, word.detail_result or {}, src_lang,
                )
                on_ready(self._anki.add_note(deck_name, fields))
            except Exception as e:
                logger.exception("save_to_anki failed for word=%r", word.text)
                on_ready({"success": False, "error": str(e)})
        threading.Thread(target=bg, daemon=True).start()
