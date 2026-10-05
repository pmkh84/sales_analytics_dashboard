"""Integration tests against PostgreSQL, isolated in a rolled-back temporary schema."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
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
