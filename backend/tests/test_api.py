"""Integration tests against PostgreSQL, isolated in a rolled-back temporary schema."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.main import app
from app.models import Customer, Product, Sale


@pytest.fixture
def client():
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
                    created_at=datetime(2025, 1, day, tzinfo=timezone.utc),
                )
            )
        db.commit()
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as test_client:
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
        **payload, "id": 3, "total_amount": 59.97,
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
    assert summary["total_revenue"] == 109.97
    assert summary["total_customers"] == 2
    recent = client.get("/api/sales/recent", params=PARAMS).json()["items"][0]
    assert recent["customer_id"] == customer.id
    assert recent["product_id"] == product.id
    assert recent["quantity"] == 3
    assert recent["total_amount"] == 59.97
    assert recent["category"] == "Books"
    trend = client.get("/api/dashboard/revenue-trend", params=PARAMS).json()
    assert trend[-1] == {"date": "2025-01-04", "revenue": 59.97, "orders": 1}
    categories = client.get("/api/dashboard/categories", params=PARAMS).json()
    assert categories == [
        {"category": "Books", "revenue": 59.97, "orders": 1, "units": 3},
        {"category": "Electronics", "revenue": 50, "orders": 1, "units": 1},
    ]
    products = client.get("/api/dashboard/top-products", params=PARAMS).json()
    assert products[0]["id"] == product.id
    assert products[0]["revenue"] == 59.97
    # Saving unchanged fields must still use the current price.
    product.price = Decimal("20.01")
    db.commit()
    assert client.patch("/api/sales/3", json=payload).json()["total_amount"] == 60.03


@pytest.mark.parametrize("sale_id,payload,detail", [
    (999, {"customer_id": 1, "product_id": 1, "quantity": 2}, "Sale not found."),
    (3, {"customer_id": 999, "product_id": 1, "quantity": 2}, "Customer not found."),
    (3, {"customer_id": 1, "product_id": 999, "quantity": 2}, "Product not found."),
])
def test_update_missing_entities(client, sale_id, payload, detail):
    response = client.patch(f"/api/sales/{sale_id}", json=payload)
    assert response.status_code == 404
    assert response.json() == {"detail": detail}
    assert client.get("/api/dashboard/summary", params=PARAMS).json()["total_revenue"] == 200


@pytest.mark.parametrize("changes", [
    {"quantity": 0}, {"quantity": -1}, {"quantity": 1.5}, {"quantity": True},
    {"quantity": "2"}, {"quantity": None}, {"quantity": 2147483648},
    {"customer_id": None}, {"product_id": 0}, {"total_amount": 1},
])
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
    response = client.options("/api/sales/3", headers={
        "Origin": get_settings().frontend_url,
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "content-type",
    })
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
    response = client.options("/api/sales/3", headers={
        "Origin": get_settings().frontend_url,
        "Access-Control-Request-Method": "DELETE",
    })
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_sale_options(client):
    assert client.get("/api/customers").json() == [{"id": 1, "name": "Test Buyer"}]
    assert client.get("/api/products").json() == [{"id": 1, "name": "Test Product", "price": 50}]


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
    assert sale["total_amount"] == 59.97
    assert sale["created_at"]
    db.expire_all()
    assert db.get(Sale, sale["id"]).total_amount == Decimal("59.97")
    after = client.get("/api/dashboard/summary").json()
    assert after["total_orders"] == before["total_orders"] + 1
    assert after["total_revenue"] == pytest.approx(before["total_revenue"] + 59.97)
    recent = client.get("/api/sales/recent").json()
    assert recent["items"][0]["id"] == sale["id"]
    assert recent["items"][0]["customer_name"] == "Test Buyer"
    trend = client.get("/api/dashboard/revenue-trend").json()
    assert sum(point["revenue"] for point in trend) == pytest.approx(after["total_revenue"])
    assert client.get("/api/dashboard/categories").json()[0]["revenue"] == 59.97
    assert client.get("/api/dashboard/top-products").json()[0]["units"] == 3


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "2", True, None, 2147483648])
def test_create_sale_invalid_quantity(client, quantity):
    assert client.post("/api/sales", json={
        "customer_id": 1, "product_id": 1, "quantity": quantity,
    }).status_code == 422
    assert client.get("/api/dashboard/summary").json()["total_orders"] == 0


@pytest.mark.parametrize("field", ["customer_id", "product_id"])
def test_create_sale_missing_entity(client, field):
    payload = {"customer_id": 1, "product_id": 1, "quantity": 1, field: 999}
    response = client.post("/api/sales", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == ("Customer not found." if field == "customer_id" else "Product not found.")
    assert client.get("/api/dashboard/summary").json()["total_orders"] == 0


def test_create_sale_rejects_client_total_and_missing_fields(client):
    assert client.post("/api/sales", json={
        "customer_id": 1, "product_id": 1, "quantity": 1, "total_amount": 0,
    }).status_code == 422
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


@pytest.mark.parametrize("sqlstate,expected", [
    ("28P01", "Database authentication failed."),
    ("3D000", "Configured database does not exist."),
    ("42P01", "Database schema is not initialized."),
    (None, "Database connection unavailable."),
])
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
