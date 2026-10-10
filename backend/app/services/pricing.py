"""Decimal pricing shared by sales and current product quotes."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from fastapi import HTTPException

from app.schemas import ExchangeRate
from app.services.exchange_rate import get_exchange_rate_service

USD_LIMIT = Decimal("999999999999.99")
TOMAN_LIMIT = Decimal("999999999999999999999999999999.99")


def current_rate() -> Decimal:
    try:
        return usable_rate(get_exchange_rate_service().get_rate())
    except HTTPException:
        raise HTTPException(
            503, "A USD/Toman rate is unavailable. Sale pricing cannot be completed."
        ) from None


def usable_rate(quote: ExchangeRate) -> Decimal:
    try:
        # Only Decimal reaches persistence; quantize first so arithmetic uses the saved rate.
        with localcontext() as context:
            context.prec = 40
            rate = quote.rate.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        if not rate.is_finite() or rate <= 0 or rate > Decimal("1000000000000"):
            raise InvalidOperation
        return rate
    except (InvalidOperation, ValueError):
        raise HTTPException(
            503, "A USD/Toman rate is unavailable. Sale pricing cannot be completed."
        ) from None


def toman_total(usd: Decimal, rate: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        total = (usd * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if total > TOMAN_LIMIT:
        raise HTTPException(422, "Toman total is too large.")
    return total


def sale_prices(price_usd: Decimal, quantity: int) -> tuple[Decimal, Decimal, Decimal]:
    total_usd = price_usd * quantity
    if total_usd > USD_LIMIT:
        raise HTTPException(422, "Quantity is too large for this product's price.")
    rate = current_rate()
    return total_usd, rate, toman_total(total_usd, rate)
