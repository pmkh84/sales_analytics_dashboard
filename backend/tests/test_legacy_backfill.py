"""Fixed-rate legacy backfill uses saved USD totals and updates API analytics."""

from decimal import Decimal

import pytest
from test_api import client as api_client
from test_api import notification_handler as api_notification_handler

from app.backfill_legacy_pricing import LEGACY_EXCHANGE_RATE_TOMAN, backfill_connection
from app.database import get_db
from app.main import app
from app.models import Sale

client = api_client
notification_handler = api_notification_handler


def test_backfill_updates_sales_and_reports_preserving_existing_prices(client, notification_handler):
    db = app.dependency_overrides[get_db]()
    existing = db.get(Sale, 3)
    before = (existing.total_amount, existing.exchange_rate_toman, existing.total_amount_toman)
    legacy = Sale(
        customer_id=1,
        product_id=1,
        quantity=2,
        # Use the saved discounted USD amount, not today's catalog price x quantity.
        total_amount=Decimal("71.10"),
        created_at=existing.created_at,
    )
    db.add(legacy)
    db.commit()
    original_date = legacy.created_at
    params = {"start_date": "2025-01-04", "end_date": "2025-01-04"}
    original_revenue = client.get("/api/dashboard/summary", params=params).json()["total_revenue"]

    assert backfill_connection(db.connection()) == 1
    db.commit()
    db.expire_all()
    assert legacy.exchange_rate_toman == LEGACY_EXCHANGE_RATE_TOMAN
    assert legacy.total_amount_toman == Decimal("18983700.00")
    assert legacy.total_amount == Decimal("71.10")
    assert legacy.quantity == 2 and legacy.created_at == original_date
    assert (existing.total_amount, existing.exchange_rate_toman, existing.total_amount_toman) == before

    summary = client.get("/api/dashboard/summary", params=params).json()
    assert summary["legacy_orders"] == 0 and summary["priced_orders"] == 2
    assert summary["total_revenue"] == original_revenue + Decimal("18983700.00")
    assert summary["average_order_value"] == summary["total_revenue"] / 2
    for endpoint in ("revenue-trend", "categories", "top-products"):
        items = client.get(f"/api/dashboard/{endpoint}", params=params).json()
        assert sum(item["revenue"] for item in items) == summary["total_revenue"]
    sales = client.get("/api/sales/recent", params=params).json()["items"]
    item = next(item for item in sales if item["id"] == legacy.id)
    assert item["total_amount_toman"] == Decimal("18983700.00")
    assert item["exchange_rate_toman"] == LEGACY_EXCHANGE_RATE_TOMAN
    assert backfill_connection(db.connection()) == 0
    notification_handler.handle.assert_not_called()


@pytest.mark.parametrize("usd", ["0.00", "79.00", "0.01", "999999999999.99"])
def test_backfill_preserves_decimal_precision(client, usd):
    db = app.dependency_overrides[get_db]()
    legacy = Sale(customer_id=1, product_id=1, quantity=1, total_amount=Decimal(usd))
    db.add(legacy)
    db.commit()
    assert backfill_connection(db.connection()) == 1
    db.commit()
    db.refresh(legacy)
    assert legacy.total_amount == Decimal(usd)
    assert legacy.exchange_rate_toman == LEGACY_EXCHANGE_RATE_TOMAN
    assert legacy.total_amount_toman == Decimal(usd) * LEGACY_EXCHANGE_RATE_TOMAN
