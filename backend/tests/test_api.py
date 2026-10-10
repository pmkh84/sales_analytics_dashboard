"""Integration tests against PostgreSQL, isolated in a rolled-back temporary schema."""

from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.events import SaleCreated, SaleDeleted, SaleUpdated
from app.main import app
from app.models import Customer, Product, Sale, TelegramSubscriber
from app.notifications import service as notifications
from app.notifications import subscriptions
from app.notifications.service import NotificationHandler
from app.notifications.telegram import TelegramClient
from app.schemas import ExchangeRate
from app.services import pricing
from app.services.exchange_rate import get_exchange_rate_service

SALE_PAYLOAD = {"customer_id": 1, "product_id": 1, "quantity": 2}
SALE_ACTIONS = [
    ("post", "/api/sales", 201, SaleCreated),
    ("patch", "/api/sales/3", 200, SaleUpdated),
    ("delete", "/api/sales/3", 204, SaleDeleted),
]


class DecimalTestClient(TestClient):
    """Decode Decimal strings for arithmetic assertions; raw JSON contract is tested separately."""

    def request(self, *args, **kwargs):
        response = super().request(*args, **kwargs)
        original_json = response.json
        money_fields = {
            "total_amount",
            "total_amount_toman",
            "exchange_rate_toman",
            "price",
            "price_usd",
            "price_toman",
            "total_revenue",
            "previous_revenue",
            "average_order_value",
            "revenue",
            "rate",
        }

        def decode(value):
            if isinstance(value, dict):
                return {
                    key: Decimal(item) if key in money_fields and isinstance(item, str) else decode(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [decode(item) for item in value]
            return value

        response.json = lambda **options: decode(original_json(**options))
        return response


@pytest.fixture(autouse=True)
def notification_handler(monkeypatch):
    # Never deliver to real Telegram, even if the developer has configured credentials.
    handler = Mock()
    monkeypatch.setattr(notifications, "get_notification_handler", lambda: handler)
    return handler


@pytest.fixture
def client(monkeypatch):
    rate_service = Mock()
    rate_service.get_rate.return_value = ExchangeRate(
        rate=Decimal("1"), updated_at=datetime.now(timezone.utc)
    )
    monkeypatch.setattr(pricing, "get_exchange_rate_service", lambda: rate_service)
    monkeypatch.setattr("app.services.sales.get_exchange_rate_service", lambda: rate_service)
    app.dependency_overrides[get_exchange_rate_service] = lambda: rate_service
    with engine.connect() as connection:
        transaction = connection.begin()
        schema = "test_" + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        Base.metadata.create_all(connection)
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        customer = Customer(name="Test Buyer", email="test@example.com")
        product = Product(name="Test Product", category="Electronics", price=Decimal("50"))
        db.add_all([customer, product])
        db.flush()
        for day, amount, quantity in [(1, "100", 2), (3, "50", 1), (4, "150", 3), (5, "999", 1)]:
            db.add(
                Sale(
                    customer_id=customer.id,
                    product_id=product.id,
                    quantity=quantity,
                    total_amount=Decimal(amount),
                    exchange_rate_toman=Decimal("1"),
                    total_amount_toman=Decimal(amount),
                    created_at=datetime(2025, 1, day, tzinfo=timezone.utc),
                )
            )
        db.commit()
        app.dependency_overrides[get_db] = lambda: db
        try:
            with DecimalTestClient(app) as test_client:
                yield test_client
        finally:
            app.dependency_overrides.clear()
            db.close()
            transaction.rollback()


PARAMS = {"start_date": "2025-01-03", "end_date": "2025-01-04"}


def test_update_sale_persists_and_updates_analytics(client):
    db = app.dependency_overrides[get_db]()
    # Duplicate names ensure the form can use IDs rather than guessing by name.
    customer = Customer(name="Test Buyer", email="second@example.com")
    product = Product(name="Test Product", category="Books", price=Decimal("19.99"))
    db.add_all([customer, product])
    db.commit()
    payload = {"customer_id": customer.id, "product_id": product.id, "quantity": 3}
    original_date = db.get(Sale, 3).created_at
    response = client.patch("/api/sales/3", json=payload)
    assert response.status_code == 200
    assert response.json() == {
        **payload,
        "id": 3,
        "total_amount": Decimal("59.97"),
        "exchange_rate_toman": Decimal("1"),
        "total_amount_toman": Decimal("59.97"),
        "created_at": original_date.isoformat().replace("+00:00", "Z"),
    }
    db.expire_all()
    sale = db.get(Sale, 3)
    assert sale.total_amount == Decimal("59.97")
    assert sale.customer_id == customer.id
    assert sale.product_id == product.id
    assert sale.quantity == 3
    assert sale.created_at == original_date
    summary = client.get("/api/dashboard/summary", params=PARAMS).json()
    assert summary["total_orders"] == 2
    assert summary["total_revenue"] == Decimal("109.97")
    assert summary["total_customers"] == 2
    recent = client.get("/api/sales/recent", params=PARAMS).json()["items"][0]
    assert recent["customer_id"] == customer.id
    assert recent["product_id"] == product.id
    assert recent["quantity"] == 3
    assert recent["total_amount"] == Decimal("59.97")
    assert recent["category"] == "Books"
    trend = client.get("/api/dashboard/revenue-trend", params=PARAMS).json()
    assert trend[-1] == {"date": "2025-01-04", "revenue": Decimal("59.97"), "orders": 1}
    categories = client.get("/api/dashboard/categories", params=PARAMS).json()
    assert categories == [
        {"category": "Books", "revenue": Decimal("59.97"), "orders": 1, "units": 3},
        {"category": "Electronics", "revenue": 50, "orders": 1, "units": 1},
    ]
    products = client.get("/api/dashboard/top-products", params=PARAMS).json()
    assert products[0]["id"] == product.id
    assert products[0]["revenue"] == Decimal("59.97")
    # Saving unchanged financial inputs preserves history even if the product price changes.
    product.price = Decimal("20.01")
    db.commit()
    assert client.patch("/api/sales/3", json=payload).json()["total_amount"] == Decimal("59.97")


@pytest.mark.parametrize(
    "sale_id,payload,detail",
    [
        (999, {"customer_id": 1, "product_id": 1, "quantity": 2}, "Sale not found."),
        (3, {"customer_id": 999, "product_id": 1, "quantity": 2}, "Customer not found."),
        (3, {"customer_id": 1, "product_id": 999, "quantity": 2}, "Product not found."),
    ],
)
def test_update_missing_entities(client, sale_id, payload, detail):
    response = client.patch(f"/api/sales/{sale_id}", json=payload)
    assert response.status_code == 404
    assert response.json() == {"detail": detail}
    assert client.get("/api/dashboard/summary", params=PARAMS).json()["total_revenue"] == 200


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": 0},
        {"quantity": -1},
        {"quantity": 1.5},
        {"quantity": True},
        {"quantity": "2"},
        {"quantity": None},
        {"quantity": 2147483648},
        {"customer_id": None},
        {"product_id": 0},
        {"total_amount": 1},
    ],
)
def test_update_invalid_fields(client, changes):
    payload = {"customer_id": 1, "product_id": 1, "quantity": 2, **changes}
    assert client.patch("/api/sales/3", json=payload).status_code == 422
    assert client.get("/api/dashboard/summary", params=PARAMS).json()["total_revenue"] == 200


def test_update_requires_all_fields_and_valid_id(client):
    assert client.patch("/api/sales/3", json={"quantity": 2}).status_code == 422
    payload = {"customer_id": 1, "product_id": 1, "quantity": 2}
    for sale_id in ["bad", "0", "-1", "1.5", "2147483648"]:
        assert client.patch(f"/api/sales/{sale_id}", json=payload).status_code == 422


def test_update_overflow_and_commit_failure_leave_sale_unchanged(client):
    db = app.dependency_overrides[get_db]()
    db.get(Product, 1).price = Decimal("9999999999.99")
    db.commit()
    payload = {"customer_id": 1, "product_id": 1, "quantity": 101}
    assert client.patch("/api/sales/3", json=payload).status_code == 422
    with patch.object(db, "commit", side_effect=SQLAlchemyError("test failure")):
        assert client.patch("/api/sales/3", json={**payload, "quantity": 1}).status_code == 503
    db.expire_all()
    assert db.get(Sale, 3).total_amount == Decimal("150")
    assert db.get(Sale, 3).quantity == 3


def test_update_cors(client):
    response = client.options(
        "/api/sales/3",
        headers={
            "Origin": get_settings().frontend_url,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_delete_sale_persists_and_updates_analytics(client):
    response = client.delete("/api/sales/3")
    assert response.status_code == 204
    assert response.content == b""
    db = app.dependency_overrides[get_db]()
    db.expire_all()
    assert db.get(Sale, 3) is None
    assert db.get(Customer, 1) is not None
    assert db.get(Product, 1) is not None
    summary = client.get("/api/dashboard/summary", params=PARAMS).json()
    assert summary["total_orders"] == 1
    assert summary["total_revenue"] == 50
    recent = client.get("/api/sales/recent", params=PARAMS).json()
    assert recent["total"] == 1
    assert [sale["id"] for sale in recent["items"]] == [2]
    assert client.get("/api/dashboard/revenue-trend", params=PARAMS).json() == [
        {"date": "2025-01-03", "revenue": 50, "orders": 1},
        {"date": "2025-01-04", "revenue": 0, "orders": 0},
    ]
    assert client.get("/api/dashboard/categories", params=PARAMS).json() == [
        {"category": "Electronics", "revenue": 50, "orders": 1, "units": 1},
    ]
    product = client.get("/api/dashboard/top-products", params=PARAMS).json()[0]
    assert product["revenue"] == 50
    assert product["units"] == 1
    assert client.delete("/api/sales/3").status_code == 404


def test_delete_missing_sale(client):
    response = client.delete("/api/sales/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Sale not found."}
    assert client.get("/api/dashboard/summary", params=PARAMS).json()["total_orders"] == 2


@pytest.mark.parametrize("sale_id", ["bad", "1.5", "0", "-1", "2147483648"])
def test_delete_invalid_id(client, sale_id):
    assert client.delete(f"/api/sales/{sale_id}").status_code == 422


def test_delete_failure_rolls_back(client):
    db = app.dependency_overrides[get_db]()
    with patch.object(db, "commit", side_effect=SQLAlchemyError("test failure")):
        assert client.delete("/api/sales/3").status_code == 503
    assert db.get(Sale, 3) is not None
    assert client.get("/api/dashboard/summary", params=PARAMS).json()["total_orders"] == 2


def test_delete_cors(client):
    response = client.options(
        "/api/sales/3",
        headers={
            "Origin": get_settings().frontend_url,
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_sale_options(client):
    assert client.get("/api/customers").json() == [{"id": 1, "name": "Test Buyer"}]
    assert client.get("/api/products").json() == [
        {
            "id": 1,
            "name": "Test Product",
            "price": 50,
            "price_usd": 50,
            "price_toman": 50,
            "exchange_rate_stale": False,
        }
    ]


def test_create_sale_persists_and_updates_analytics(client):
    db = app.dependency_overrides[get_db]()
    db.get(Product, 1).price = Decimal("19.99")
    db.commit()
    before = client.get("/api/dashboard/summary").json()
    response = client.post("/api/sales", json={"customer_id": 1, "product_id": 1, "quantity": 3})
    assert response.status_code == 201
    sale = response.json()
    assert sale["customer_id"] == sale["product_id"] == 1
    assert sale["quantity"] == 3
    assert sale["total_amount"] == Decimal("59.97")
    assert sale["created_at"]
    db.expire_all()
    assert db.get(Sale, sale["id"]).total_amount == Decimal("59.97")
    after = client.get("/api/dashboard/summary").json()
    assert after["total_orders"] == before["total_orders"] + 1
    assert after["total_revenue"] == pytest.approx(before["total_revenue"] + Decimal("59.97"))
    recent = client.get("/api/sales/recent").json()
    assert recent["items"][0]["id"] == sale["id"]
    assert recent["items"][0]["customer_name"] == "Test Buyer"
    trend = client.get("/api/dashboard/revenue-trend").json()
    assert sum(point["revenue"] for point in trend) == pytest.approx(after["total_revenue"])
    assert client.get("/api/dashboard/categories").json()[0]["revenue"] == Decimal("59.97")
    assert client.get("/api/dashboard/top-products").json()[0]["units"] == 3


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "2", True, None, 2147483648])
def test_create_sale_invalid_quantity(client, quantity):
    assert (
        client.post(
            "/api/sales",
            json={
                "customer_id": 1,
                "product_id": 1,
                "quantity": quantity,
            },
        ).status_code
        == 422
    )
    assert client.get("/api/dashboard/summary").json()["total_orders"] == 0


@pytest.mark.parametrize("field", ["customer_id", "product_id"])
def test_create_sale_missing_entity(client, field):
    payload = {"customer_id": 1, "product_id": 1, "quantity": 1, field: 999}
    response = client.post("/api/sales", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Customer not found." if field == "customer_id" else "Product not found."
    )
    assert client.get("/api/dashboard/summary").json()["total_orders"] == 0


def test_create_sale_rejects_client_total_and_missing_fields(client):
    assert (
        client.post(
            "/api/sales",
            json={
                "customer_id": 1,
                "product_id": 1,
                "quantity": 1,
                "total_amount": 0,
            },
        ).status_code
        == 422
    )
    assert client.post("/api/sales", json={"quantity": 1}).status_code == 422


def test_create_sale_rejects_total_overflow(client):
    db = app.dependency_overrides[get_db]()
    db.get(Product, 1).price = Decimal("9999999999.99")
    db.commit()
    response = client.post("/api/sales", json={"customer_id": 1, "product_id": 1, "quantity": 101})
    assert response.status_code == 422


def test_summary_and_equal_length_growth(client):
    response = client.get("/api/dashboard/summary", params=PARAMS)
    assert response.status_code == 200
    data = response.json()
    assert data["total_revenue"] == 200
    assert data["total_orders"] == 2
    assert data["total_customers"] == 1
    assert data["average_order_value"] == 100
    assert data["previous_revenue"] == 100
    assert data["revenue_growth"] == 100


def test_trend_zero_fills_and_months(client):
    data = client.get(
        "/api/dashboard/revenue-trend", params={"start_date": "2025-01-01", "end_date": "2025-01-04"}
    ).json()
    assert [point["revenue"] for point in data] == [100, 0, 50, 150]
    monthly = client.get("/api/dashboard/revenue-trend", params={**PARAMS, "interval": "month"}).json()
    assert monthly == [{"date": "2025-01-01", "revenue": 200, "orders": 2}]


def test_category_product_and_pagination(client):
    category = client.get("/api/dashboard/categories", params=PARAMS).json()[0]
    assert category == {"category": "Electronics", "revenue": 200, "orders": 2, "units": 4}
    product = client.get("/api/dashboard/top-products", params=PARAMS).json()[0]
    assert product["revenue"] == 200
    assert product["units"] == 4
    sales = client.get("/api/sales/recent", params={**PARAMS, "limit": 1, "offset": 1}).json()
    assert sales["total"] == 2
    assert sales["items"][0]["total_amount"] == 50


def test_empty_period(client):
    params = {"start_date": "2024-01-01", "end_date": "2024-01-02"}
    data = client.get("/api/dashboard/summary", params=params).json()
    assert data["total_orders"] == 0
    assert data["average_order_value"] == 0
    assert data["revenue_growth"] is None
    assert client.get("/api/dashboard/categories", params=params).json() == []
    assert client.get("/api/sales/recent", params=params).json()["items"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2025-02-01", "end_date": "2025-01-01"},
        {"start_date": "2020-01-01", "end_date": "2025-01-01"},
        {"start_date": "bad"},
        {"start_date": "0001-01-01", "end_date": "0001-01-02"},
        {"end_date": "9999-12-31"},
        {"end_date": "0001-01-01"},
    ],
)
def test_invalid_dates(client, params):
    assert client.get("/api/dashboard/summary", params=params).status_code == 422


def test_validation_and_cors(client):
    assert client.get("/api/sales/recent", params={"limit": 0}).status_code == 422
    assert client.post("/api/ai/ask", json={"question": "  "}).status_code == 422
    response = client.options(
        "/api/ai/ask",
        headers={
            "Origin": get_settings().frontend_url,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == get_settings().frontend_url
    blocked = client.options(
        "/api/ai/ask",
        headers={
            "Origin": "https://not-allowed.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert blocked.status_code == 400


def test_missing_ai_key(client):
    with patch.object(get_settings(), "openai_api_key", ""):
        assert client.get("/api/ai/insights", params=PARAMS).status_code == 503
        assert (
            client.post("/api/ai/ask", params=PARAMS, json={"question": "Top category?"}).status_code == 503
        )


def test_ai_uses_aggregates_only(client):
    with patch.object(get_settings(), "openai_api_key", "test-key"):
        with patch("app.ai.service.OpenAI") as mock:
            create = mock.return_value.__enter__.return_value.responses.create
            create.return_value = SimpleNamespace(status="completed", output_text="Electronics leads.")
            response = client.post("/api/ai/ask", params=PARAMS, json={"question": "Top category?"})
            assert response.status_code == 200
            assert response.json()["answer"] == "Electronics leads."
            payload = create.call_args.kwargs["input"]
            assert "Electronics" in payload
            assert "Test Buyer" not in payload
            assert "test@example.com" not in payload
            assert create.call_args.kwargs["store"] is False


def test_insights_contract_and_invalid_output(client):
    with patch.object(get_settings(), "openai_api_key", "test-key"):
        with patch("app.ai.service.OpenAI") as mock:
            create = mock.return_value.__enter__.return_value.responses.create
            create.return_value = SimpleNamespace(
                status="completed",
                output_text='{"insights":[{"title":"Revenue","detail":"Revenue is $200."},'
                '{"title":"Category","detail":"Electronics leads."},'
                '{"title":"Attention","detail":"Review category concentration."}]}',
            )
            assert client.get("/api/ai/insights", params=PARAMS).status_code == 200
            create.return_value = SimpleNamespace(status="completed", output_text="invalid json")
            assert client.get("/api/ai/insights", params=PARAMS).status_code == 502


def test_database_failure_is_sanitized(client):
    from sqlalchemy.exc import OperationalError

    def unavailable():
        raise OperationalError("secret SQL", {}, Exception("secret password"))

    app.dependency_overrides[get_db] = unavailable
    response = client.get("/api/health")
    assert response.status_code == 503
    assert "secret" not in response.text


def test_health_checks_application_schema(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"


@pytest.mark.parametrize("table", ["customers", "products", "sales"])
def test_health_rejects_missing_application_tables(client, table):
    db = app.dependency_overrides[get_db]()
    # The fixture's search_path points only to its isolated, rolled-back test schema.
    db.execute(text(f'DROP TABLE "{table}" CASCADE'))
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["detail"] == "Database schema is not initialized. Run python -m app.seed."


@pytest.mark.parametrize(
    "sqlstate,expected",
    [
        ("28P01", "Database authentication failed."),
        ("3D000", "Configured database does not exist."),
        ("42P01", "Database schema is not initialized."),
        (None, "Database connection unavailable."),
    ],
)
def test_database_errors_are_actionable_without_leaking_secrets(client, sqlstate, expected):
    from sqlalchemy.exc import OperationalError

    def unavailable():
        error = Exception("private credentials")
        error.sqlstate = sqlstate
        raise OperationalError("private SQL", {}, error)

    app.dependency_overrides[get_db] = unavailable
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["detail"].startswith(expected)
    assert "private" not in response.text


def _sale_action(client, method, path):
    kwargs = {} if method == "delete" else {"json": SALE_PAYLOAD}
    return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize("method,path,status,event_type", SALE_ACTIONS)
def test_notification_follows_commit_and_has_database_snapshot(
    client,
    notification_handler,
    method,
    path,
    status,
    event_type,
):
    db = app.dependency_overrides[get_db]()
    original_commit, original_refresh = db.commit, db.refresh
    order = []

    def commit():
        original_commit()
        order.append("committed")

    def refresh(*args, **kwargs):
        original_refresh(*args, **kwargs)
        order.append("refreshed")

    def notified(event):
        assert order == (["committed"] if method == "delete" else ["committed", "refreshed"])
        assert isinstance(event, event_type)
        snapshot = event.sale
        stored = db.get(Sale, snapshot.id)
        if method == "delete":
            assert stored is None
            assert snapshot.quantity == 3
            assert snapshot.total_amount == Decimal("150")
        else:
            assert stored.quantity == snapshot.quantity == 2
            assert stored.total_amount == snapshot.total_amount == Decimal("100")
        assert snapshot.product_name == "Test Product"
        assert snapshot.category == "Electronics"
        assert snapshot.customer_id == snapshot.product_id == 1
        if method == "patch":
            assert event.previous.quantity == 3
            assert event.previous.total_amount == Decimal("150")
        order.append("notified")

    notification_handler.handle.side_effect = notified
    with patch.object(db, "commit", side_effect=commit), patch.object(db, "refresh", side_effect=refresh):
        assert _sale_action(client, method, path).status_code == status
    notification_handler.handle.assert_called_once()
    assert order[-1] == "notified"


@pytest.mark.parametrize("method,path,status,event_type", SALE_ACTIONS)
def test_commit_failure_rolls_back_without_notification(
    client,
    notification_handler,
    method,
    path,
    status,
    event_type,
):
    db = app.dependency_overrides[get_db]()
    original_count = db.scalar(text("SELECT count(*) FROM sales"))
    with patch.object(db, "commit", side_effect=SQLAlchemyError("private failure")):
        response = _sale_action(client, method, path)
    assert response.status_code == 503
    notification_handler.handle.assert_not_called()
    assert db.scalar(text("SELECT count(*) FROM sales")) == original_count
    assert db.get(Sale, 3).quantity == 3
    assert db.get(Sale, 3).total_amount == Decimal("150")


def test_create_flush_failure_does_not_notify(client, notification_handler):
    db = app.dependency_overrides[get_db]()
    with patch.object(db, "flush", side_effect=SQLAlchemyError("test failure")):
        assert _sale_action(client, "post", "/api/sales").status_code == 503
    notification_handler.handle.assert_not_called()
    assert db.scalar(text("SELECT count(*) FROM sales")) == 4


@pytest.mark.parametrize("method,path,status,event_type", SALE_ACTIONS[:2])
def test_refresh_failure_does_not_notify(client, notification_handler, method, path, status, event_type):
    db = app.dependency_overrides[get_db]()
    with patch.object(db, "refresh", side_effect=SQLAlchemyError("test failure")):
        assert _sale_action(client, method, path).status_code == 503
    notification_handler.handle.assert_not_called()


@pytest.mark.parametrize(
    "method,path,payload,status",
    [
        ("post", "/api/sales", {**SALE_PAYLOAD, "customer_id": 999}, 404),
        ("patch", "/api/sales/3", {**SALE_PAYLOAD, "product_id": 999}, 404),
        ("patch", "/api/sales/999", SALE_PAYLOAD, 404),
        ("delete", "/api/sales/999", None, 404),
        ("post", "/api/sales", {**SALE_PAYLOAD, "quantity": 0}, 422),
        ("patch", "/api/sales/3", {**SALE_PAYLOAD, "quantity": 0}, 422),
        ("delete", "/api/sales/0", None, 422),
    ],
)
def test_business_validation_failure_does_not_notify(
    client, notification_handler, method, path, payload, status
):
    kwargs = {} if payload is None else {"json": payload}
    assert getattr(client, method)(path, **kwargs).status_code == status
    notification_handler.handle.assert_not_called()


@pytest.mark.parametrize("method,path,status,event_type", SALE_ACTIONS)
@pytest.mark.parametrize("failure", ["http", "timeout", "api", "invalid_json", "unexpected"])
def test_telegram_failure_preserves_api_success_and_data(
    client,
    monkeypatch,
    caplog,
    method,
    path,
    status,
    event_type,
    failure,
):
    original_client = httpx.Client
    requests = []

    def respond(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private credentials", request=request)
        if failure == "unexpected":
            raise RuntimeError("private credentials")
        if failure == "invalid_json":
            return httpx.Response(200, text="private response")
        return httpx.Response(
            500 if failure == "http" else 200, json={"ok": False, "description": "private response"}
        )

    monkeypatch.setattr(
        "app.notifications.telegram.httpx.Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(respond),
            trust_env=False,
        ),
    )
    handler = NotificationHandler(
        TelegramClient(
            "synthetic-marker",
            "https://example.invalid",
            1,
        ),
        lambda: [7],
    )
    monkeypatch.setattr(notifications, "get_notification_handler", lambda: handler)
    response = _sale_action(client, method, path)
    assert response.status_code == status
    assert len(requests) == 1
    assert "private" not in caplog.text
    assert "synthetic-marker" not in caplog.text
    assert f"event={event_type.__name__}" in caplog.text
    assert "sale_id=" in caplog.text
    assert "synthetic" not in response.text
    db = app.dependency_overrides[get_db]()
    db.expire_all()
    if method == "delete":
        assert db.get(Sale, 3) is None
    else:
        stored = db.get(Sale, response.json()["id"])
        assert stored.quantity == 2
        assert stored.total_amount == Decimal("100")


@pytest.mark.parametrize("method,path,status,event_type", SALE_ACTIONS)
def test_missing_notification_config_preserves_api_success(
    client, monkeypatch, method, path, status, event_type
):
    monkeypatch.setattr(notifications, "get_notification_handler", lambda: None)
    assert _sale_action(client, method, path).status_code == status


@pytest.mark.parametrize("method,path,status,event_type", SALE_ACTIONS)
def test_successful_api_operation_delivers_expected_message(
    client, monkeypatch, method, path, status, event_type
):
    original_client = httpx.Client
    messages = []

    def respond(request):
        import json

        messages.append(json.loads(request.content)["text"])
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(
        "app.notifications.telegram.httpx.Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(respond),
            trust_env=False,
        ),
    )
    handler = NotificationHandler(
        TelegramClient(
            "synthetic-marker",
            "https://example.invalid",
            1,
        ),
        lambda: [7],
    )
    monkeypatch.setattr(notifications, "get_notification_handler", lambda: handler)
    assert _sale_action(client, method, path).status_code == status
    assert len(messages) == 1
    message = messages[0]
    if method == "post":
        assert "Sale Created (Sold)" in message
        assert "Quantity: 2" in message
        assert "Total (USD): 100.00" in message
    elif method == "patch":
        assert "Sale Updated" in message
        assert "Quantity: 3 \u2192 2" in message
        assert "Total (USD): 150.00 \u2192 100.00" in message
    else:
        assert "Sale Deleted" in message
        assert "Product: Test Product (#1)" in message
        assert "Quantity: 3" in message
    assert "Test Buyer" not in message
    assert "test@example.com" not in message


def _telegram_command(client, command, chat_id=9000000001, **metadata):
    return client.post(
        "/api/telegram/webhook",
        json={
            "update_id": 1,
            "message": {"chat": {"id": chat_id, "type": "private", **metadata}, "text": command},
        },
    )


@pytest.mark.parametrize("chat_id", [123, 9000000001, -1009000000001])
def test_start_accepts_any_chat_without_authorization(client, notification_handler, chat_id):
    response = _telegram_command(
        client, "/start", chat_id, username="demo", first_name="Demo", last_name="User"
    )
    assert response.status_code == 200 and response.json() == {"ok": True}
    db = app.dependency_overrides[get_db]()
    subscriber = db.get(TelegramSubscriber, chat_id)
    assert subscriber.is_active
    assert (subscriber.username, subscriber.first_name, subscriber.last_name) == ("demo", "Demo", "User")
    assert subscriber.chat_type == "private"
    notification_handler.confirm_subscription.assert_called_once_with(chat_id, True)


@pytest.mark.parametrize("command", ["/start", "/start@DemoBot", "/start ignored-argument"])
def test_start_upserts_refreshes_metadata_and_preserves_missing_metadata(
    client, notification_handler, command
):
    db = app.dependency_overrides[get_db]()
    assert _telegram_command(client, "/start", username="old", first_name="Original").status_code == 200
    created = db.get(TelegramSubscriber, 9000000001).created_at
    assert _telegram_command(client, command, username="new").status_code == 200
    db.expire_all()
    subscriber = db.get(TelegramSubscriber, 9000000001)
    assert subscriber.username == "new" and subscriber.first_name == "Original"
    assert subscriber.created_at == created
    assert subscriber.updated_at >= created
    assert db.scalar(text("SELECT count(*) FROM telegram_subscribers")) == 1
    assert notification_handler.confirm_subscription.call_count == 2


def test_stop_then_start_reactivates_same_subscriber(client, notification_handler):
    db = app.dependency_overrides[get_db]()
    assert _telegram_command(client, "/start").status_code == 200
    assert _telegram_command(client, "/stop").status_code == 200
    db.expire_all()
    assert not db.get(TelegramSubscriber, 9000000001).is_active
    notification_handler.confirm_subscription.assert_called_with(9000000001, False)
    assert _telegram_command(client, "/start", first_name="Updated").status_code == 200
    db.expire_all()
    assert db.get(TelegramSubscriber, 9000000001).is_active
    assert db.get(TelegramSubscriber, 9000000001).first_name == "Updated"
    assert db.scalar(text("SELECT count(*) FROM telegram_subscribers")) == 1
    notification_handler.confirm_subscription.assert_called_with(9000000001, True)


def test_stop_unknown_chat_confirms_without_creating_subscription(client, notification_handler):
    assert _telegram_command(client, "/stop").status_code == 200
    db = app.dependency_overrides[get_db]()
    assert db.get(TelegramSubscriber, 9000000001) is None
    notification_handler.confirm_subscription.assert_called_once_with(9000000001, False)


@pytest.mark.parametrize(
    "payload",
    [
        {"update_id": 1, "callback_query": {"data": "anything"}},
        {"update_id": 1},
        {"update_id": 1, "message": {"chat": {"id": 123, "type": "private"}, "photo": []}},
        {"update_id": 1, "message": {"chat": {"id": 123, "type": "private"}, "text": "   "}},
        {"update_id": 1, "message": {"chat": {"id": 123, "type": "private"}, "text": "/help"}},
        {"update_id": 1, "message": {"chat": {"id": 123, "type": "private"}, "text": "say /start"}},
    ],
)
def test_other_telegram_updates_are_ignored(client, notification_handler, payload):
    assert client.post("/api/telegram/webhook", json=payload).status_code == 200
    notification_handler.confirm_subscription.assert_not_called()
    db = app.dependency_overrides[get_db]()
    assert subscriptions.active_chat_ids(db) == []


@pytest.mark.parametrize("command,active", [("/start", True), ("/stop", False)])
def test_subscription_confirmation_is_after_commit(client, notification_handler, command, active):
    db = app.dependency_overrides[get_db]()
    _telegram_command(client, "/start")
    notification_handler.reset_mock()
    original_commit = db.commit
    committed = False

    def commit():
        nonlocal committed
        original_commit()
        committed = True

    def confirmed(chat_id, is_active):
        assert committed
        assert db.get(TelegramSubscriber, chat_id).is_active == is_active == active

    notification_handler.confirm_subscription.side_effect = confirmed
    with patch.object(db, "commit", side_effect=commit):
        assert _telegram_command(client, command).status_code == 200
    notification_handler.confirm_subscription.assert_called_once_with(9000000001, active)


@pytest.mark.parametrize("command", ["/start", "/stop"])
def test_subscription_commit_failure_rolls_back_and_skips_confirmation(client, notification_handler, command):
    db = app.dependency_overrides[get_db]()
    if command == "/stop":
        _telegram_command(client, "/start")
        notification_handler.reset_mock()
    with patch.object(db, "commit", side_effect=SQLAlchemyError("private failure")):
        assert _telegram_command(client, command).status_code == 503
    notification_handler.confirm_subscription.assert_not_called()
    db.expire_all()
    subscriber = db.get(TelegramSubscriber, 9000000001)
    assert subscriber is None if command == "/start" else subscriber.is_active


@pytest.mark.parametrize("command", ["/start", "/stop"])
@pytest.mark.parametrize("failure", ["http", "unexpected"])
def test_confirmation_failure_preserves_subscription_state(client, monkeypatch, caplog, command, failure):
    db = app.dependency_overrides[get_db]()
    if command == "/stop":
        _telegram_command(client, "/start")
    original_client = httpx.Client

    def respond(request):
        if failure == "unexpected":
            raise RuntimeError("private failure")
        return httpx.Response(500, json={"ok": False})

    monkeypatch.setattr(
        "app.notifications.telegram.httpx.Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(respond),
            trust_env=False,
        ),
    )
    handler = NotificationHandler(TelegramClient("synthetic-marker", "https://example.invalid", 1))
    monkeypatch.setattr(notifications, "get_notification_handler", lambda: handler)
    assert _telegram_command(client, command).status_code == 200
    db.expire_all()
    assert db.get(TelegramSubscriber, 9000000001).is_active == (command == "/start")
    assert "Telegram delivery failed" in caplog.text
    assert "private failure" not in caplog.text and "synthetic-marker" not in caplog.text


def test_subscription_persists_when_telegram_is_disabled(client, monkeypatch):
    monkeypatch.setattr(notifications, "get_notification_handler", lambda: None)
    assert _telegram_command(client, "/start").status_code == 200
    db = app.dependency_overrides[get_db]()
    assert db.get(TelegramSubscriber, 9000000001).is_active


@pytest.mark.parametrize("method,path,status,event_type", SALE_ACTIONS)
def test_sales_broadcast_to_active_subscribers_only(client, monkeypatch, method, path, status, event_type):
    db = app.dependency_overrides[get_db]()
    _telegram_command(client, "/start", 11)
    _telegram_command(client, "/start", 22)
    _telegram_command(client, "/start", 33)
    _telegram_command(client, "/stop", 22)
    transport = Mock()
    handler = NotificationHandler(transport, lambda: subscriptions.active_chat_ids(db))
    monkeypatch.setattr(notifications, "get_notification_handler", lambda: handler)
    assert _sale_action(client, method, path).status_code == status
    assert [entry.args[1] for entry in transport.send_message.call_args_list] == [11, 33]
    assert (
        transport.send_message.call_args_list[0].args[0] == transport.send_message.call_args_list[1].args[0]
    )


def test_group_chat_metadata_is_supported(client):
    assert (
        _telegram_command(client, "/start", -1009000000001, type="supergroup", title="Demo Group").status_code
        == 200
    )
    db = app.dependency_overrides[get_db]()
    subscriber = db.get(TelegramSubscriber, -1009000000001)
    assert subscriber.chat_type == "supergroup" and subscriber.title == "Demo Group"


def test_default_broadcast_queries_current_subscriptions_each_time(client, monkeypatch):
    db = app.dependency_overrides[get_db]()
    _telegram_command(client, "/start", 11)
    monkeypatch.setattr(subscriptions, "SessionLocal", lambda: nullcontext(db))
    transport = Mock()
    handler = NotificationHandler(transport)
    monkeypatch.setattr(notifications, "get_notification_handler", lambda: handler)
    assert _sale_action(client, "post", "/api/sales").status_code == 201
    assert transport.send_message.call_args.args[1] == 11
    assert _telegram_command(client, "/stop", 11).status_code == 200
    transport.reset_mock()
    assert _sale_action(client, "post", "/api/sales").status_code == 201
    transport.send_message.assert_not_called()


def test_subscriber_query_failure_preserves_successful_sale(client, monkeypatch, caplog):
    def unavailable():
        raise SQLAlchemyError("private database error")

    transport = Mock()
    handler = NotificationHandler(transport, unavailable)
    monkeypatch.setattr(notifications, "get_notification_handler", lambda: handler)
    response = _sale_action(client, "post", "/api/sales")
    assert response.status_code == 201
    transport.send_message.assert_not_called()
    assert "event=SaleCreated" in caplog.text and "error_type=SQLAlchemyError" in caplog.text
    assert "private database error" not in caplog.text
    db = app.dependency_overrides[get_db]()
    assert db.get(Sale, response.json()["id"]).quantity == 2
