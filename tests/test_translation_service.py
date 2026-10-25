import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "App"))

from services.translation_service import TranslationService


class EmptyTranslationCache:
    def get_translation(self, text, source, target):
        return None

    def save_translation(self, text, source, target, result):
        pass


class TranslationServiceTests(unittest.TestCase):
    @patch("services.cache_service.CacheService.get", return_value=EmptyTranslationCache())
    @patch("services.translation_service.GoogleTranslator")
    def test_translation_failure_is_reported_to_callback(self, translator, _cache):
        translator.return_value.translate.side_effect = RuntimeError("network unavailable")
        results = []
        service = TranslationService()
        service._pending_text = "Olá."
        service._pending_callback = results.append

        service._do_translate()

        self.assertEqual(results, ["Translation unavailable"])

    @patch("services.cache_service.CacheService.get", return_value=EmptyTranslationCache())
    @patch("services.translation_service.GoogleTranslator")
    def test_translation_success_reaches_callback(self, translator, _cache):
        translator.return_value.translate.return_value = "Hello."
        results = []
        service = TranslationService()
        service._pending_text = "Olá."
        service._pending_callback = results.append

        service._do_translate()

        self.assertEqual(results, ["Hello."])


if __name__ == "__main__":
    unittest.main()
