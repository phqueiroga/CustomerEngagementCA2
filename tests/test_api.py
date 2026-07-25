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


if __name__ == "__main__":
    unittest.main()

