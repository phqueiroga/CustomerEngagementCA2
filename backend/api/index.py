import json
import os
from http.server import BaseHTTPRequestHandler
from typing import Any


def _integer_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def allowed_origins() -> set[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    return {origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()}


def validate_messages(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        raise ValueError("The request body must be a JSON object.")

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("'messages' must be a non-empty array.")
    if len(messages) > 40:
        raise ValueError("The conversation is too long. Start a new chat.")

    maximum_total = _integer_setting(
        "MAX_INPUT_CHARACTERS", default=12000, minimum=1000, maximum=100000
    )
    cleaned: list[dict[str, str]] = []
    total = 0

    for item in messages:
        if not isinstance(item, dict):
            raise ValueError("Every message must be an object.")
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            raise ValueError("Message roles must be 'user' or 'assistant'.")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Every message must contain non-empty text.")

        content = content.strip()
        if len(content) > 4000:
            raise ValueError("An individual message is too long.")
        total += len(content)
        if total > maximum_total:
            raise ValueError("The conversation exceeds the input limit.")
        cleaned.append({"role": role, "content": content})

    if cleaned[-1]["role"] != "user":
        raise ValueError("The final message must be from the user.")
    return cleaned


def create_reply(messages: list[dict[str, str]]) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    model = os.environ.get("ANTHROPIC_MODEL")
    if not api_key or not model:
        raise RuntimeError("The server is missing required configuration.")

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key, timeout=30.0, max_retries=1)
    result = client.messages.create(
        model=model,
        max_tokens=_integer_setting(
            "MAX_OUTPUT_TOKENS", default=600, minimum=1, maximum=4096
        ),
        system=(
            "You are a helpful customer assistant. Be concise, truthful, and "
            "friendly. If you do not know something, say so."
        ),
        messages=messages,
    )
    text = "".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        raise RuntimeError("The model returned no text.")
    return text


class handler(BaseHTTPRequestHandler):
    server_version = "CustomerChatAPI/1.0"

    def _origin(self) -> str:
        return (self.headers.get("Origin") or "").rstrip("/")

    def _origin_is_allowed(self) -> bool:
        origin = self._origin()
        return bool(origin) and origin in allowed_origins()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Origin")
        if self._origin_is_allowed():
            self.send_header("Access-Control-Allow-Origin", self._origin())
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        if not self._origin_is_allowed():
            self._send_json(403, {"error": "Origin is not allowed."})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self._origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        self._send_json(200, {"status": "ok"})

    def do_POST(self) -> None:
        if self.headers.get("Origin") and not self._origin_is_allowed():
            self._send_json(403, {"error": "Origin is not allowed."})
            return
        if "application/json" not in (self.headers.get("Content-Type") or "").lower():
            self._send_json(415, {"error": "Content-Type must be application/json."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "Invalid Content-Length."})
            return
        if content_length <= 0 or content_length > 150_000:
            self._send_json(413, {"error": "Request body is empty or too large."})
            return

        try:
            payload = json.loads(self.rfile.read(content_length))
            messages = validate_messages(payload)
            reply = create_reply(messages)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "The request body is not valid JSON."})
            return
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return
        except RuntimeError as error:
            self._send_json(503, {"error": str(error)})
            return
        except Exception:
            self._send_json(502, {"error": "The language model request failed."})
            return

        self._send_json(200, {"reply": reply})

    def log_message(self, format: str, *args: Any) -> None:
        # Avoid logging request bodies or secrets. Vercel still records platform logs.
        super().log_message(format, *args)

