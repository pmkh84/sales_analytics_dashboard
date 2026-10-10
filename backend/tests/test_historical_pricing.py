"""Historical pricing integration tests in the existing rolled-back PostgreSQL schema."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from test_api import client as api_client
from test_api import notification_handler as api_notification_handler

from app.database import get_db
from app.main import app
from app.migrate import migrate_connection
from app.models import Customer, Product, Sale
from app.notifications.service import format_message
from app.schemas import ExchangeRate
from app.services import pricing
from app.services.analytics import analytics_context, resolve_period

client = api_client
notification_handler = api_notification_handler


@pytest.fixture
def rates(client):
    service = pricing.get_exchange_rate_service()
    service.get_rate.return_value = ExchangeRate(rate=Decimal("100"), updated_at=datetime.now(timezone.utc))
    db = app.dependency_overrides[get_db]()
    db.get(Product, 1).price = Decimal("2.00")
    db.commit()
    service.reset_mock()
    return service


def quote(service, value, stale=False):
    service.get_rate.return_value = ExchangeRate(
        rate=Decimal(value),
        updated_at=datetime.now(timezone.utc),
        stale=stale,
    )


def create(client, quantity=1, product=1):
    return client.post("/api/sales", json={"customer_id": 1, "product_id": product, "quantity": quantity})


def test_two_rates_preserve_history_and_sum_saved_toman(client, rates, notification_handler):
    first = create(client)
    assert first.status_code == 201
    # Raw wire contract preserves exact decimal strings, not binary floats.
    raw = httpx.Response.json(first)
    assert raw["total_amount"] == "2.00"
    assert raw["exchange_rate_toman"] == "100.000000"
    assert raw["total_amount_toman"] == "200.00"
    quote(rates, "150")
    second = create(client)
    assert second.json()["total_amount_toman"] == Decimal("300.00")
    rates.get_rate.reset_mock()
    rates.get_rate.side_effect = HTTPException(503, "not available")
    items = client.get("/api/sales/recent").json()["items"]
    assert {item["id"]: item["total_amount_toman"] for item in items} == {
        first.json()["id"]: Decimal("200"),
        second.json()["id"]: Decimal("300"),
    }
    summary = client.get("/api/dashboard/summary").json()
    assert summary["total_revenue"] == Decimal("500")
    assert summary["average_order_value"] == Decimal("250")
    assert summary["priced_orders"] == 2 and summary["legacy_orders"] == 0
    assert sum(item["revenue"] for item in client.get("/api/dashboard/revenue-trend").json()) == 500
    assert client.get("/api/dashboard/categories").json()[0]["revenue"] == 500
    assert client.get("/api/dashboard/top-products").json()[0]["revenue"] == 500
    rates.get_rate.assert_not_called()
    db = app.dependency_overrides[get_db]()
    assert db.get(Product, 1).price == Decimal("2.00")
    first_event, second_event = [call.args[0] for call in notification_handler.handle.call_args_list]
    assert "Total (Toman): 200.00" in format_message(first_event)
    assert "Total (Toman): 300.00" in format_message(second_event)
    assert "Exchange rate (Toman): 100" in format_message(first_event)


@pytest.mark.parametrize("product_change", [False, True])
def test_financial_update_uses_current_rate(client, rates, product_change):
    original = create(client).json()
    db = app.dependency_overrides[get_db]()
    product_id, quantity, expected = 1, 3, Decimal("900")
    if product_change:
        product = Product(name="Another", category="Books", price=Decimal("3"))
        db.add(product)
        db.commit()
        product_id, quantity, expected = product.id, 1, Decimal("450")
    quote(rates, "150")
    result = client.patch(
        f"/api/sales/{original['id']}",
        json={
            "customer_id": 1,
            "product_id": product_id,
            "quantity": quantity,
        },
    )
    assert result.status_code == 200
    assert result.json()["total_amount_toman"] == expected
    assert result.json()["exchange_rate_toman"] == Decimal("150")
    assert result.json()["created_at"] == original["created_at"]


def test_customer_only_and_unchanged_edits_preserve_history_without_rate(client, rates):
    original = create(client).json()
    db = app.dependency_overrides[get_db]()
    buyer = Customer(name="Other", email="other@example.com")
    db.add(buyer)
    db.get(Product, 1).price = Decimal("9")
    db.commit()
    rates.get_rate.reset_mock()
    rates.get_rate.side_effect = HTTPException(503, "unavailable")
    for customer_id in (buyer.id, buyer.id):
        response = client.patch(
            f"/api/sales/{original['id']}",
            json={
                "customer_id": customer_id,
                "product_id": 1,
                "quantity": 1,
            },
        )
        assert response.status_code == 200
        for key in ("total_amount", "exchange_rate_toman", "total_amount_toman"):
            assert response.json()[key] == original[key]
    rates.get_rate.assert_not_called()


@pytest.mark.parametrize("update", [False, True])
def test_no_rate_prevents_partial_write_or_notification(client, rates, notification_handler, update):
    db = app.dependency_overrides[get_db]()
    original = create(client).json()
    count = db.scalar(select(func.count(Sale.id)))
    notification_handler.reset_mock()
    rates.get_rate.side_effect = HTTPException(503, "private provider data")
    result = (
        client.patch(
            f"/api/sales/{original['id']}",
            json={
                "customer_id": 1,
                "product_id": 1,
                "quantity": 2,
            },
        )
        if update
        else create(client)
    )
    assert result.status_code == 503
    assert "Sale pricing cannot be completed" in result.json()["detail"]
    assert "private" not in result.text
    notification_handler.handle.assert_not_called()
    db.expire_all()
    sale = db.get(Sale, original["id"])
    assert db.scalar(select(func.count(Sale.id))) == count
    assert (sale.quantity, sale.total_amount, sale.exchange_rate_toman, sale.total_amount_toman) == (
        1,
        Decimal("2"),
        Decimal("100"),
        Decimal("200"),
    )


@pytest.mark.parametrize("update", [False, True])
def test_database_failure_rolls_back_all_financial_fields(client, rates, notification_handler, update):
    original = create(client).json()
    db = app.dependency_overrides[get_db]()
    count = db.scalar(select(func.count(Sale.id)))
    quote(rates, "150")
    notification_handler.reset_mock()
    with patch.object(db, "commit", side_effect=SQLAlchemyError("private")):
        result = (
            client.patch(
                f"/api/sales/{original['id']}",
                json={
                    "customer_id": 1,
                    "product_id": 1,
                    "quantity": 2,
                },
            )
            if update
            else create(client)
        )
    assert result.status_code == 503
    db.expire_all()
    sale = db.get(Sale, original["id"])
    assert (sale.total_amount, sale.exchange_rate_toman, sale.total_amount_toman) == (
        Decimal("2"),
        Decimal("100"),
        Decimal("200"),
    )
    assert db.scalar(select(func.count(Sale.id))) == count
    notification_handler.handle.assert_not_called()


def test_fractional_rate_quantized_before_multiplication_and_stale_accepted(client, rates):
    quote(rates, "100.1234567", stale=True)
    result = create(client, quantity=3)
    assert result.status_code == 201
    data = result.json()
    assert data["exchange_rate_toman"] == Decimal("100.123457")
    assert data["total_amount"] == Decimal("6")
    assert data["total_amount_toman"] == Decimal("600.74")
    assert data["total_amount_toman"] == pricing.toman_total(
        data["total_amount"], data["exchange_rate_toman"]
    )


def test_tiny_rate_cannot_round_to_zero(client, rates):
    quote(rates, "0.0000001")
    assert create(client).status_code == 503


def test_current_product_price_changes_without_overwriting_usd(client, rates):
    first = client.get("/api/products").json()[0]
    assert first["price_usd"] == 2 and first["price_toman"] == 200
    quote(rates, "150", stale=True)
    second = client.get("/api/products").json()[0]
    assert second["price_usd"] == first["price_usd"] == 2
    assert second["price_toman"] == 300 and second["exchange_rate_stale"] is True
    rates.get_rate.side_effect = HTTPException(503, "private")
    unavailable = client.get("/api/products")
    assert unavailable.status_code == 200
    assert unavailable.json()[0]["price_toman"] is None
    assert unavailable.json()[0]["price_usd"] == 2


def test_legacy_amounts_unavailable_and_excluded_from_revenue_and_aov(client, rates):
    create(client)
    db = app.dependency_overrides[get_db]()
    legacy = Sale(customer_id=1, product_id=1, quantity=1, total_amount=Decimal("10000"))
    db.add(legacy)
    db.commit()
    rates.get_rate.reset_mock()
    summary = client.get("/api/dashboard/summary").json()
    assert summary["total_orders"] == 2 and summary["priced_orders"] == 1 and summary["legacy_orders"] == 1
    assert summary["total_revenue"] == summary["average_order_value"] == 200
    assert summary["revenue_growth"] is None
    items = client.get("/api/sales/recent").json()["items"]
    old = next(item for item in items if item["id"] == legacy.id)
    assert old["total_amount_toman"] is None and old["exchange_rate_toman"] is None
    assert old["total_amount"] == 10000
    # No-op edits do not silently backfill the legacy sale either.
    assert (
        client.patch(
            f"/api/sales/{legacy.id}",
            json={
                "customer_id": 1,
                "product_id": 1,
                "quantity": 1,
            },
        ).json()["total_amount_toman"]
        is None
    )
    rates.get_rate.assert_not_called()


def test_previous_period_and_growth_use_historical_toman_and_coverage(client, rates):
    first = create(client).json()
    db = app.dependency_overrides[get_db]()
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    db.get(Sale, first["id"]).created_at = yesterday
    db.commit()
    quote(rates, "150")
    create(client)
    today = datetime.now(timezone.utc).date().isoformat()
    params = {"start_date": today, "end_date": today}
    result = client.get("/api/dashboard/summary", params=params).json()
    assert result["total_revenue"] == 300 and result["previous_revenue"] == 200
    assert result["revenue_growth"] == 50
    db.add(Sale(customer_id=1, product_id=1, quantity=1, total_amount=Decimal("99"), created_at=yesterday))
    db.commit()
    result = client.get("/api/dashboard/summary", params=params).json()
    assert result["previous_legacy_orders"] == 1 and result["revenue_growth"] is None
    context = analytics_context(
        db, resolve_period(datetime.now(timezone.utc).date(), datetime.now(timezone.utc).date())
    )
    assert context["currency"] == "IRT"
    assert "legacy" in context["definitions"]["money_coverage"].lower()


def test_update_and_delete_notifications_use_saved_amounts(client, rates, notification_handler):
    sale = create(client).json()
    quote(rates, "150")
    response = client.patch(
        f"/api/sales/{sale['id']}", json={"customer_id": 1, "product_id": 1, "quantity": 2}
    )
    assert response.status_code == 200
    event = notification_handler.handle.call_args.args[0]
    message = format_message(event)
    assert "Total (Toman): 200.00 \u2192 600.00" in message
    assert "Exchange rate (Toman): 100 \u2192 150" in message
    rates.get_rate.side_effect = HTTPException(503, "unavailable")
    assert client.delete(f"/api/sales/{sale['id']}").status_code == 204
    assert "Total (Toman): 600.00" in format_message(notification_handler.handle.call_args.args[0])


@pytest.mark.parametrize(
    "fields",
    [
        {"exchange_rate_toman": Decimal("100"), "total_amount_toman": None},
        {"exchange_rate_toman": None, "total_amount_toman": Decimal("200")},
        {"exchange_rate_toman": Decimal("100"), "total_amount_toman": Decimal("999")},
        {"exchange_rate_toman": Decimal("0"), "total_amount_toman": Decimal("0")},
    ],
)
def test_database_rejects_partial_or_inconsistent_financial_fields(client, rates, fields):
    db = app.dependency_overrides[get_db]()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(Sale(customer_id=1, product_id=1, quantity=1, total_amount=Decimal("2"), **fields))
        db.flush()


def test_additive_migration_preserves_old_rows_and_is_idempotent(client):
    # This connection's search_path is the fixture's unique rolled-back test schema.
    db = app.dependency_overrides[get_db]()
    connection = db.connection()
    before = connection.execute(text("SELECT id, total_amount FROM sales ORDER BY id")).all()
    connection.execute(text("ALTER TABLE sales DROP CONSTRAINT historical_pricing_consistent"))
    connection.execute(
        text("ALTER TABLE sales DROP COLUMN exchange_rate_toman, DROP COLUMN total_amount_toman")
    )
    migrate_connection(connection)
    migrate_connection(connection)
    after = connection.execute(text("SELECT id, total_amount FROM sales ORDER BY id")).all()
    assert after == before
    assert (
        connection.scalar(
            text(
                "SELECT count(*) FROM sales WHERE total_amount_toman IS NULL AND exchange_rate_toman IS NULL"
            )
        )
        == 4
    )


@pytest.mark.parametrize("field", ["exchange_rate_toman", "total_amount_toman", "total_amount_usd"])
def test_clients_cannot_supply_financial_values(client, rates, field):
    response = client.post(
        "/api/sales", json={"customer_id": 1, "product_id": 1, "quantity": 1, field: "100"}
    )
    assert response.status_code == 422
