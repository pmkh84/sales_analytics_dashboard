"""Read Navasan's Tehran USD sell rate through a bounded in-process cache."""

import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Literal

import httpx
from fastapi import HTTPException

from app.config import Settings, get_settings
from app.schemas import ExchangeRate

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    def __init__(self, reason: str, status_code: int | None = None):
        self.reason = reason
        self.status_code = status_code
        super().__init__(reason)


class _RedactAPIKey(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = re.sub(r"(?i)(api_key=)[^&\s\"'<>]+", r"\1[REDACTED]", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def normalize_to_toman(value: str | int | float | Decimal, unit: Literal["IRR", "IRT"]) -> Decimal:
    """Never infer currency units from magnitude; use the provider's documented unit."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ProviderError("invalid_rate")
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ProviderError("invalid_rate") from None
    if unit not in {"IRR", "IRT"} or not amount.is_finite() or amount <= 0:
        raise ProviderError("invalid_rate")
    amount = amount / Decimal(10) if unit == "IRR" else amount
    if amount > Decimal("1000000000000"):
        raise ProviderError("invalid_rate")
    return amount


class ExchangeRateService:
    def __init__(self, settings: Settings, clock: Callable[[], float] = monotonic):
        self._settings = settings
        self._clock = clock
        self._lock = Lock()
        self._cached: ExchangeRate | None = None
        self._next_fetch = 0.0
        self._stale = False
        # Navasan requires api_key in the query; httpx otherwise logs it at INFO.
        request_logger = logging.getLogger("httpx")
        if not any(isinstance(item, _RedactAPIKey) for item in request_logger.filters):
            request_logger.addFilter(_RedactAPIKey())

    def get_rate(self) -> ExchangeRate:
        with self._lock:
            if self._clock() >= self._next_fetch:
                try:
                    self._cached = self._fetch()
                    self._stale = False
                except ProviderError as exc:
                    self._stale = True
                    logger.warning(
                        "Exchange rate provider failed: source=Navasan reason=%s status_code=%s cached=%s",
                        exc.reason,
                        exc.status_code,
                        self._cached is not None,
                    )
                # Failures are also throttled, avoiding repeated calls during an outage.
                self._next_fetch = self._clock() + self._settings.exchange_rate_cache_ttl_seconds
            if self._cached is None:
                raise HTTPException(503, "Exchange rate unavailable. Try again later.")
            return self._cached.model_copy(update={"stale": self._stale})

    def _fetch(self) -> ExchangeRate:
        token = self._settings.exchange_rate_api_key.get_secret_value().strip()
        if not token:
            raise ProviderError("not_configured")
        try:
            with httpx.Client(
                timeout=self._settings.exchange_rate_timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = client.get(
                    self._settings.exchange_rate_api_url,
                    params={"api_key": token, "item": "usd_buy"},
                )
            if not response.is_success:
                raise ProviderError("http_status", response.status_code)
            payload = response.json()
            entry = payload["usd_buy"]
            # Navasan's usd_buy is denominated in Toman; do not divide it again.
            rate = normalize_to_toman(entry["value"], "IRT")
            timestamp = entry["timestamp"]
            if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp <= 0:
                raise ProviderError("invalid_timestamp")
            updated_at = datetime.fromtimestamp(timestamp, timezone.utc)
            if updated_at > datetime.now(timezone.utc):
                raise ProviderError("invalid_timestamp")
            return ExchangeRate(rate=float(rate), updated_at=updated_at)
        except httpx.HTTPError:
            raise ProviderError("transport_error") from None
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            raise ProviderError("invalid_response") from None


@lru_cache
def get_exchange_rate_service() -> ExchangeRateService:
    return ExchangeRateService(get_settings())
