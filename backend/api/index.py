import csv
import io
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.request import Request, urlopen


CATALOGUE_TOOL = {
    "name": "get_live_catalogue",
    "description": (
        "Fetch the current Emerald Pantry product catalogue directly from its "
        "assigned Google Sheet. Use this tool for every question about products, "
        "prices, stock, availability, barcodes, offers, categories, units, or "
        "catalogue descriptions. It returns fresh CSV data for this request."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "A short explanation of what catalogue facts are needed.",
            }
        },
        "required": ["reason"],
    },
}

REQUIRED_CATALOGUE_COLUMNS = {
    "sku",
    "product_name",
    "category",
    "barcode",
    "price_eur",
    "unit",
    "availability",
    "stock_this_week",
    "special_offer",
    "description",
}


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


def fetch_live_catalogue() -> tuple[str, dict[str, str]]:
    source_url = os.environ.get("GOOGLE_SHEET_CSV_URL", "").strip()
    if not source_url.startswith("https://docs.google.com/spreadsheets/"):
        raise RuntimeError("The live catalogue source is not configured.")

    request = Request(
        source_url,
        headers={
            "User-Agent": "EmeraldPantryChatbot/1.0",
            "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urlopen(request, timeout=12) as response:
        payload = response.read(150_001)
    if len(payload) > 150_000:
        raise RuntimeError("The live catalogue response is too large.")

    csv_text = payload.decode("utf-8-sig")
    catalogue_rows = list(csv.DictReader(io.StringIO(csv_text)))
    columns = set(catalogue_rows[0]) if catalogue_rows else set()
    if not REQUIRED_CATALOGUE_COLUMNS.issubset(columns):
        raise RuntimeError("The live catalogue has an unexpected format.")

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    offer_count = sum(
        bool((row.get("special_offer") or "").strip()) for row in catalogue_rows
    )
    data_quality_warnings = []
    for row in catalogue_rows:
        sku = (row.get("sku") or "Unknown SKU").strip()
        product_name = (row.get("product_name") or "Unknown product").strip()
        try:
            price = float((row.get("price_eur") or "").strip())
        except ValueError:
            price = 0
        try:
            stock = int((row.get("stock_this_week") or "").strip())
        except ValueError:
            stock = -1
        availability = (row.get("availability") or "").strip()

        if price >= 1_000:
            data_quality_warnings.append(
                f"{sku} ({product_name}) has an implausibly high listed price "
                f"of EUR {price:,.0f}. Report it exactly, label it implausible, "
                "and recommend human verification."
            )
        if stock == 0 and availability.casefold() == "in stock":
            data_quality_warnings.append(
                f"{sku} ({product_name}) is marked 'In stock' but "
                "stock_this_week is 0. Explicitly call this an internal source "
                "inconsistency and recommend checking with staff."
            )

    warning_text = "\n".join(
        f"- {warning}" for warning in data_quality_warnings
    ) or "- None detected."
    metadata = {
        "source": "Emerald Pantry Google Sheet",
        "source_url": source_url,
        "fetched_at": fetched_at,
    }
    tool_content = (
        "LIVE SOURCE: Emerald Pantry assigned Google Sheet\n"
        f"FETCHED_AT_UTC: {fetched_at}\n"
        f"SOURCE_URL: {source_url}\n"
        f"SPECIAL_OFFER_ROW_COUNT: {offer_count}\n"
        f"LIVE_DATA_QUALITY_WARNINGS:\n{warning_text}\n"
        "The following CSV was fetched for this request. Report its values "
        "faithfully and do not silently correct surprising data.\n\n"
        f"{csv_text}"
    )
    return tool_content, metadata


def create_reply(
    messages: list[dict[str, str]],
) -> tuple[str, dict[str, str] | None]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    model = os.environ.get("ANTHROPIC_MODEL")
    if not api_key or not model:
        raise RuntimeError("The server is missing required configuration.")

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key, timeout=30.0, max_retries=1)
    max_tokens = _integer_setting(
        "MAX_OUTPUT_TOKENS", default=600, minimum=1, maximum=4096
    )
    system_prompt = (
        "You are the AI customer-support assistant for Emerald Pantry, an Irish "
        "online grocery and specialty-food business. Be warm, concise, and "
        "truthful. Write clear plain text without Markdown formatting. A live "
        "catalogue tool is available. For every question involving products, "
        "prices, stock, availability, barcodes, special offers, categories, "
        "units, or catalogue descriptions, you MUST call get_live_catalogue in "
        "that turn before answering, even if similar information appeared "
        "earlier. Never answer current catalogue facts from memory. Treat the "
        "tool output as the assigned live source and report it faithfully. If "
        "values conflict or look surprising, state what the source says and "
        "explicitly flag the inconsistency rather than explaining it away. "
        "Recommend human verification for an implausible price or contradictory "
        "availability. Do not infer how long an offer will run, whether it will "
        "apply when stock returns, or a discounted final price unless the live "
        "source explicitly provides that fact. If "
        "you list catalogue rows, do not introduce the list with a numeric count "
        "unless you have verified that it exactly matches the items listed. If "
        "the tool fails, say that live catalogue information is temporarily "
        "unavailable; never guess. For general or off-topic questions, answer "
        "naturally without calling the catalogue unless current product data is "
        "needed. Do not claim to be human."
    )
    working_messages: list[dict[str, Any]] = list(messages)
    live_data: dict[str, str] | None = None
    result = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        tools=[CATALOGUE_TOOL],
        tool_choice={"type": "auto", "disable_parallel_tool_use": True},
        messages=working_messages,
    )

    for _ in range(2):
        tool_uses = [
            block for block in result.content if getattr(block, "type", None) == "tool_use"
        ]
        if not tool_uses:
            break

        tool_results = []
        for tool_use in tool_uses:
            if tool_use.name != "get_live_catalogue":
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": "Unknown tool.",
                        "is_error": True,
                    }
                )
                continue
            try:
                tool_content, live_data = fetch_live_catalogue()
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": tool_content,
                    }
                )
            except Exception:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": "The assigned live Google Sheet could not be fetched.",
                        "is_error": True,
                    }
                )

        working_messages.extend(
            [
                {"role": "assistant", "content": result.content},
                {"role": "user", "content": tool_results},
            ]
        )
        result = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=[CATALOGUE_TOOL],
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            messages=working_messages,
        )

    text = "".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        raise RuntimeError("The model returned no text.")
    return text, live_data


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
            reply, live_data = create_reply(messages)
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

        response: dict[str, Any] = {"reply": reply}
        if live_data:
            response["live_data"] = live_data
        self._send_json(200, response)

    def log_message(self, format: str, *args: Any) -> None:
        # Avoid logging request bodies or secrets. Vercel still records platform logs.
        super().log_message(format, *args)
