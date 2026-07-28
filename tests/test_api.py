import importlib.util
import os
import pathlib
import unittest
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).parents[1] / "backend" / "api" / "index.py"
SPEC = importlib.util.spec_from_file_location("chat_api", MODULE_PATH)
chat_api = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(chat_api)


class ValidateMessagesTests(unittest.TestCase):
    def test_accepts_valid_conversation(self):
        messages = chat_api.validate_messages(
            {
                "messages": [
                    {"role": "user", "content": " Hello "},
                    {"role": "assistant", "content": "Hi"},
                    {"role": "user", "content": "Help me"},
                ]
            }
        )
        self.assertEqual(messages[0]["content"], "Hello")

    def test_rejects_unknown_role(self):
        with self.assertRaisesRegex(ValueError, "roles"):
            chat_api.validate_messages(
                {"messages": [{"role": "system", "content": "No"}]}
            )

    def test_requires_user_as_final_message(self):
        with self.assertRaisesRegex(ValueError, "final"):
            chat_api.validate_messages(
                {
                    "messages": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi"},
                    ]
                }
            )

    def test_enforces_total_character_limit(self):
        with patch.dict(os.environ, {"MAX_INPUT_CHARACTERS": "1000"}):
            with self.assertRaisesRegex(ValueError, "input limit"):
                chat_api.validate_messages(
                    {
                        "messages": [
                            {"role": "user", "content": "x" * 700},
                            {"role": "assistant", "content": "y" * 400},
                            {"role": "user", "content": "finish"},
                        ]
                    }
                )


class ConfigurationTests(unittest.TestCase):
    def test_parses_allowed_origins(self):
        with patch.dict(
            os.environ,
            {"ALLOWED_ORIGINS": "http://localhost:8000, https://example.github.io/"},
        ):
            self.assertEqual(
                chat_api.allowed_origins(),
                {"http://localhost:8000", "https://example.github.io"},
            )

    def test_missing_provider_configuration_fails_safely(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "missing required"):
                chat_api.create_reply([{"role": "user", "content": "Hello"}])


class LiveCatalogueTests(unittest.TestCase):
    def test_fetches_and_validates_live_csv_without_cache_headers(self):
        csv_text = (
            "sku,product_name,category,barcode,price_eur,unit,availability,"
            "stock_this_week,special_offer,description\n"
            "EP-1,Test Oats,pantry,123,3,500g,In stock,5,,Fresh oats\n"
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return csv_text.encode()

        with patch.dict(
            os.environ,
            {
                "GOOGLE_SHEET_CSV_URL": (
                    "https://docs.google.com/spreadsheets/d/test/export?format=csv"
                )
            },
        ):
            with patch.object(chat_api, "urlopen", return_value=FakeResponse()) as mocked:
                content, metadata = chat_api.fetch_live_catalogue()

        request = mocked.call_args.args[0]
        self.assertEqual(request.get_header("Cache-control"), "no-cache")
        self.assertIn("Test Oats", content)
        self.assertIn("SPECIAL_OFFER_ROW_COUNT: 0", content)
        self.assertIn("LIVE_DATA_QUALITY_WARNINGS:\n- None detected.", content)
        self.assertEqual(metadata["source"], "Emerald Pantry Google Sheet")
        self.assertIn("fetched_at", metadata)

    def test_flags_live_price_and_stock_anomalies(self):
        csv_text = (
            "sku,product_name,category,barcode,price_eur,unit,availability,"
            "stock_this_week,special_offer,description\n"
            "EP-1,Test Preserve,pantry,123,2900450,340g,In stock,12,,Test\n"
            "EP-2,Test Biscuits,bakery,456,4,pack,In stock,0,20% off,Test\n"
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return csv_text.encode()

        with patch.dict(
            os.environ,
            {
                "GOOGLE_SHEET_CSV_URL": (
                    "https://docs.google.com/spreadsheets/d/test/export?format=csv"
                )
            },
        ):
            with patch.object(chat_api, "urlopen", return_value=FakeResponse()):
                content, _metadata = chat_api.fetch_live_catalogue()

        self.assertIn("EUR 2,900,450", content)
        self.assertIn("stock_this_week is 0", content)
        self.assertIn("internal source inconsistency", content)

    def test_rejects_unexpected_catalogue_format(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return b"name,price\nUnknown,4\n"

        with patch.dict(
            os.environ,
            {
                "GOOGLE_SHEET_CSV_URL": (
                    "https://docs.google.com/spreadsheets/d/test/export?format=csv"
                )
            },
        ):
            with patch.object(chat_api, "urlopen", return_value=FakeResponse()):
                with self.assertRaisesRegex(RuntimeError, "unexpected format"):
                    chat_api.fetch_live_catalogue()


if __name__ == "__main__":
    unittest.main()
