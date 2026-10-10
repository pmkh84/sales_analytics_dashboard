"""Translate sale events to safe, structured Telegram messages."""

import logging
from collections.abc import Callable
from functools import lru_cache

from app.config import get_settings
from app.events import SaleCreated, SaleDeleted, SaleEvent, SaleSnapshot, SaleUpdated
from app.notifications.telegram import TelegramClient, TelegramError

logger = logging.getLogger(__name__)


def _text(value: str) -> str:
    # Database names are untrusted. Keep each value on one line, with bounded length.
    return " ".join(value.split())[:150]


def _fields(sale: SaleSnapshot) -> dict[str, str]:
    return {
        "Customer ID": f"#{sale.customer_id}",
        "Product": f"{_text(sale.product_name)} (#{sale.product_id})",
        "Category": _text(sale.category),
        "Quantity": str(sale.quantity),
        "Total (USD)": f"{sale.total_amount:.2f}",
        "Exchange rate (Toman)": (
            f"{sale.exchange_rate_toman:,.6f}".rstrip("0").rstrip(".")
            if sale.exchange_rate_toman is not None
            else "Unavailable (legacy)"
        ),
        "Total (Toman)": (
            f"{sale.total_amount_toman:,.2f}"
            if sale.total_amount_toman is not None
            else "Unavailable (legacy)"
        ),
    }


def format_message(event: SaleEvent) -> str:
    if isinstance(event, SaleCreated):
        title = "\U0001f7e2 Sale Created (Sold)"
    elif isinstance(event, SaleDeleted):
        title = "\U0001f5d1 Sale Deleted"
    else:
        title = "\u270f\ufe0f Sale Updated"
    lines = [title, "", f"Sale ID: #{event.sale.id}"]
    current = _fields(event.sale)
    if isinstance(event, SaleUpdated):
        previous = _fields(event.previous)
        lines.extend(["", "Changed fields:"])
        lines.extend(
            f"{label}: {previous[label]} \u2192 {value}"
            for label, value in current.items()
            if previous[label] != value
        )
        if current == previous:
            lines.append("No business values changed.")
    else:
        lines.extend(f"{label}: {value}" for label, value in current.items())
    return "\n".join(lines)


class NotificationHandler:
    def __init__(self, client: TelegramClient, recipients: Callable[[], list[int]] | None = None):
        self._client = client
        self._recipients = recipients

    def handle(self, event: SaleEvent) -> None:
        from app.notifications.subscriptions import active_chat_ids

        message = format_message(event)
        recipients = self._recipients or active_chat_ids
        for chat_id in recipients():
            self._send(message, chat_id, type(event).__name__, event.sale.id)

    def confirm_subscription(self, chat_id: int, active: bool) -> None:
        message = (
            "Subscribed! You will receive sale notifications. Send /stop to unsubscribe."
            if active
            else "Unsubscribed. Send /start to subscribe again."
        )
        self._send(message, chat_id, "SubscriptionStarted" if active else "SubscriptionStopped")

    def _send(self, message: str, chat_id: int, event_type: str, sale_id: int | None = None) -> None:
        try:
            self._client.send_message(message, chat_id)
        except TelegramError as exc:
            logger.warning(
                "Telegram delivery failed: event=%s sale_id=%s reason=%s status_code=%s",
                event_type,
                sale_id,
                exc.reason,
                exc.status_code,
            )
        except Exception as exc:
            logger.warning(
                "Telegram delivery failed: event=%s sale_id=%s error_type=%s",
                event_type,
                sale_id,
                type(exc).__name__,
            )


@lru_cache
def get_notification_handler() -> NotificationHandler | None:
    settings = get_settings()
    if not settings.telegram_enabled:
        logger.info("Telegram notifications disabled by TELEGRAM_ENABLED.")
        return None
    token = settings.telegram_bot_token.get_secret_value().strip()
    if not token:
        logger.warning("Telegram notifications disabled: configure TELEGRAM_BOT_TOKEN on the backend.")
        return None
    return NotificationHandler(
        TelegramClient(
            token,
            settings.telegram_api_url,
            settings.telegram_timeout_seconds,
        )
    )
