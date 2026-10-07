"""Synchronous Telegram transport. No database or business responsibilities."""

import logging
import re

import httpx


class TelegramError(Exception):
    """A sanitized transport/API failure; never includes response bodies or URLs."""

    def __init__(self, reason: str, status_code: int | None = None):
        self.reason = reason
        self.status_code = status_code
        super().__init__(reason)


class _RedactBotURL(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = re.sub(r"/bot[^/\s?]+(?=/)", "/bot[REDACTED]", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class TelegramClient:
    def __init__(self, token: str, api_url: str, timeout: float):
        self._base_url = f"{api_url.rstrip('/')}/bot{token}"
        self._timeout = timeout
        # httpx logs full request URLs at INFO; Telegram puts credentials in the path.
        request_logger = logging.getLogger("httpx")
        if not any(isinstance(item, _RedactBotURL) for item in request_logger.filters):
            request_logger.addFilter(_RedactBotURL())

    def send_message(self, message: str, chat_id: int | str) -> None:
        self._request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": message,
                "link_preview_options": {"is_disabled": True},
            },
        )

    def set_webhook(self, url: str) -> None:
        self._request("setWebhook", {"url": url, "allowed_updates": ["message"], "max_connections": 1})

    def _request(self, method: str, payload: dict) -> None:
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
                response = client.post(f"{self._base_url}/{method}", json=payload)
            if not response.is_success:
                raise TelegramError("http_status", response.status_code)
            result = response.json()
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise TelegramError("api_rejected")
        except httpx.HTTPError:
            raise TelegramError("transport_error") from None
        except ValueError:
            raise TelegramError("invalid_response") from None
