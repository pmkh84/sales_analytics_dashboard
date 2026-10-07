"""Immutable business events and a best-effort, in-process publisher."""

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SaleSnapshot:
    id: int
    customer_id: int
    product_id: int
    product_name: str
    category: str
    quantity: int
    total_amount: Decimal


@dataclass(frozen=True)
class SaleCreated:
    sale: SaleSnapshot


@dataclass(frozen=True)
class SaleUpdated:
    sale: SaleSnapshot
    previous: SaleSnapshot


@dataclass(frozen=True)
class SaleDeleted:
    sale: SaleSnapshot


SaleEvent = SaleCreated | SaleUpdated | SaleDeleted


def publish(event: SaleEvent) -> None:
    """Call only after commit. A secondary handler must never undo API success."""
    try:
        # Lazy composition keeps business services independent of delivery channels.
        from app.notifications.service import get_notification_handler

        handler = get_notification_handler()
        if handler is not None:
            handler.handle(event)
    except Exception as exc:
        # Exception messages/tracebacks can contain credentials, URLs or customer data.
        logger.warning(
            "Notification failed: event=%s sale_id=%s error_type=%s",
            type(event).__name__,
            event.sale.id,
            type(exc).__name__,
        )
