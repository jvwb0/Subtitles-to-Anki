# controllers/definition_controller.py
"""Fetches word definitions/grammar in background threads for the GUI."""

import threading

from interfaces.definition_provider import IDefinitionProvider
from utils.app_logger import get_logger

logger = get_logger(__name__)


class DefinitionController:
    def __init__(self, definition_provider: IDefinitionProvider):
        self._definitions = definition_provider

    def fetch_hover_definition(self, word, src_lang, tgt_lang, on_ready):
        """Fetch simple definition in a background thread.
        Stores result on word.simple_result, then calls on_ready(word) on the BG thread."""
        def bg():
            try:
                word.simple_result = self._definitions.fetch_definition(word.text, src_lang, tgt_lang)
                on_ready(word)
            except Exception:
                logger.exception("fetch_hover_definition failed for word=%r", word.text)
        threading.Thread(target=bg, daemon=True).start()

    def fetch_full_definition(self, word, src_lang, tgt_lang, on_ready):
        """Fetch simple + detailed definition in a background thread.
        Stores results on word, then calls on_ready(word) on the BG thread."""
        def bg():
            try:
                word.simple_result = self._definitions.fetch_definition(word.text, src_lang, tgt_lang)
                word.detail_result = self._definitions.fetch_details(word.text, src_lang, tgt_lang)
                on_ready(word)
            except Exception:
                logger.exception("fetch_full_definition failed for word=%r", word.text)
        threading.Thread(target=bg, daemon=True).start()
