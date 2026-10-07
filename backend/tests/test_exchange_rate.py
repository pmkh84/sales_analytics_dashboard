"""Exchange-rate unit/API tests; provider calls always use MockTransport."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.services import exchange_rate
from app.services.exchange_rate import ExchangeRateService, ProviderError, normalize_to_toman

TIMESTAMP = 1609459200  # Historical fixture, independent of the machine's current date.
PAYLOAD = {"usd_buy": {"value": "115000", "timestamp": TIMESTAMP}}


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        exchange_rate_api_key=SecretStr("synthetic-exchange-marker"),
        exchange_rate_api_url="https://rates.example.invalid/latest/",
        exchange_rate_cache_ttl_seconds=120,
        exchange_rate_timeout_seconds=5,
    )


@pytest.fixture
def provider(monkeypatch):
    original_client = httpx.Client
    responses = [httpx.Response(200, json=PAYLOAD)]
    requests = []

    def respond(request):
        requests.append(request)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    factory = Mock(
        side_effect=lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(respond),
            trust_env=False,
        )
    )
    monkeypatch.setattr(exchange_rate.httpx, "Client", factory)
    return responses, requests, factory


@pytest.fixture
def clock():
    return [0.0]


def test_provider_payload_is_toman_and_uses_provider_update_time(settings, provider, clock, caplog):
    service = ExchangeRateService(settings, lambda: clock[0])
    with caplog.at_level(logging.INFO):
        rate = service.get_rate()
    assert rate.rate == 115000
    assert rate.base == "USD" and rate.quote == "IRT" and rate.source == "Navasan"
    assert rate.updated_at == datetime.fromtimestamp(TIMESTAMP, timezone.utc)
    assert not rate.stale
    requests, factory = provider[1:]
    assert requests[0].url.params["item"] == "usd_buy"
    assert requests[0].url.params["api_key"] == "synthetic-exchange-marker"
    assert factory.call_args.kwargs == {"timeout": 5, "follow_redirects": False}
    assert "synthetic-exchange-marker" not in caplog.text
    assert "api_key=[REDACTED]" in caplog.text


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        ("1150000", "IRR", Decimal("115000")),
        ("1150001", "IRR", Decimal("115000.1")),
        ("115000", "IRT", Decimal("115000")),
        (Decimal("115000.25"), "IRT", Decimal("115000.25")),
    ],
)
def test_normalization_uses_explicit_unit(value, unit, expected):
    assert normalize_to_toman(value, unit) == expected


@pytest.mark.parametrize("value", [None, True, 0, -1, "", "invalid", "NaN", "Infinity", "1e100", {}])
def test_invalid_rate_is_never_returned(value):
    with pytest.raises(ProviderError):
        normalize_to_toman(value, "IRT")


def test_unknown_currency_unit_is_rejected():
    with pytest.raises(ProviderError):
        normalize_to_toman("115000", "USD")


def test_fresh_cache_is_reused_and_exact_expiry_fetches_again(settings, provider, clock):
    service = ExchangeRateService(settings, lambda: clock[0])
    first = service.get_rate()
    clock[0] = 119.9
    assert service.get_rate() == first
    assert len(provider[1]) == 1
    provider[0].append(
        httpx.Response(200, json={"usd_buy": {"value": "116000", "timestamp": TIMESTAMP + 60}})
    )
    clock[0] = 120
    assert service.get_rate().rate == 116000
    assert len(provider[1]) == 2


def test_custom_ttl_is_respected(settings, provider, clock):
    settings.exchange_rate_cache_ttl_seconds = 300
    service = ExchangeRateService(settings, lambda: clock[0])
    service.get_rate()
    clock[0] = 299
    service.get_rate()
    assert len(provider[1]) == 1


def test_failure_returns_stale_preserves_timestamp_throttles_and_recovers(settings, provider, clock, caplog):
    service = ExchangeRateService(settings, lambda: clock[0])
    initial = service.get_rate()
    provider[0].append(httpx.Response(503, json={"error": "private provider data"}))
    clock[0] = 120
    stale = service.get_rate()
    assert stale.stale and stale.rate == initial.rate and stale.updated_at == initial.updated_at
    clock[0] = 239
    assert service.get_rate() == stale
    assert len(provider[1]) == 2
    assert "reason=http_status status_code=503 cached=True" in caplog.text
    assert "private provider data" not in caplog.text
    provider[0].append(httpx.Response(200, json=PAYLOAD))
    clock[0] = 240
    assert not service.get_rate().stale
    assert len(provider[1]) == 3


def test_failure_without_cache_returns_sanitized_503_and_is_throttled(settings, provider, clock, caplog):
    provider[0][:] = [httpx.ReadTimeout("private URL and credentials")]
    service = ExchangeRateService(settings, lambda: clock[0])
    for _ in range(2):
        with pytest.raises(HTTPException) as caught:
            service.get_rate()
        assert caught.value.status_code == 503
        assert caught.value.detail == "Exchange rate unavailable. Try again later."
    assert len(provider[1]) == 1
    assert "private" not in caplog.text and "synthetic-exchange-marker" not in caplog.text
    provider[0].append(httpx.Response(200, json=PAYLOAD))
    clock[0] = 120
    assert not service.get_rate().stale


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"error": "private credential"}),
        httpx.Response(429, json={"error": "private quota"}),
        httpx.Response(302, headers={"location": "https://other.example.invalid"}),
        httpx.Response(200, text="not JSON"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"usd_buy": None}),
        httpx.Response(200, json={"usd_buy": {"value": "0", "timestamp": TIMESTAMP}}),
        httpx.Response(200, json={"usd_buy": {"value": "115000"}}),
        httpx.Response(200, json={"usd_buy": {"value": "115000", "timestamp": True}}),
        httpx.Response(200, json={"usd_buy": {"value": "115000", "timestamp": "invalid"}}),
        httpx.Response(200, json={"usd_buy": {"value": "115000", "timestamp": 999999999999999999}}),
    ],
)
def test_provider_errors_and_invalid_payloads_are_secondary_failures(settings, provider, clock, response):
    service = ExchangeRateService(settings, lambda: clock[0])
    initial = service.get_rate()
    clock[0] = 120
    provider[0].append(response)
    fallback = service.get_rate()
    assert fallback.stale and fallback.rate == initial.rate


def test_missing_optional_configuration_never_calls_provider(settings, provider, caplog):
    settings.exchange_rate_api_key = SecretStr("")
    with pytest.raises(HTTPException) as caught:
        ExchangeRateService(settings).get_rate()
    assert caught.value.status_code == 503
    assert not provider[1]
    assert "reason=not_configured" in caplog.text


def test_concurrent_requests_share_one_fetch(settings, provider):
    service = ExchangeRateService(settings)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: service.get_rate(), range(8)))
    assert all(result.rate == 115000 for result in results)
    assert len(provider[1]) == 1


def test_endpoint_response_shape_and_stale_fallback(settings, provider, clock, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "get_notification_handler", lambda: None)
    service = ExchangeRateService(settings, lambda: clock[0])
    main.app.dependency_overrides[exchange_rate.get_exchange_rate_service] = lambda: service
    try:
        with TestClient(main.app) as client:
            result = client.get("/api/exchange-rate")
            assert result.status_code == 200
            assert result.json() == {
                "base": "USD",
                "quote": "IRT",
                "rate": 115000,
                "updated_at": datetime.fromtimestamp(TIMESTAMP, timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "source": "Navasan",
                "stale": False,
            }
            clock[0] = 120
            provider[0].append(httpx.Response(500))
            result = client.get("/api/exchange-rate")
            assert result.status_code == 200 and result.json()["stale"] is True
            assert "synthetic" not in result.text
    finally:
        main.app.dependency_overrides.pop(exchange_rate.get_exchange_rate_service)


def test_endpoint_no_cache_failure_is_nonblocking(settings, provider, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "get_notification_handler", lambda: None)
    provider[0][:] = [httpx.Response(500)]
    service = ExchangeRateService(settings)
    main.app.dependency_overrides[exchange_rate.get_exchange_rate_service] = lambda: service
    try:
        with TestClient(main.app) as client:
            response = client.get("/api/exchange-rate")
            assert response.status_code == 503
            assert response.json() == {"detail": "Exchange rate unavailable. Try again later."}
            assert client.get("/openapi.json").status_code == 200
    finally:
        main.app.dependency_overrides.pop(exchange_rate.get_exchange_rate_service)


@pytest.mark.parametrize(
    "changes",
    [
        {"exchange_rate_api_url": "http://example.invalid"},
        {"exchange_rate_api_url": "https://user:password@example.invalid"},
        {"exchange_rate_api_url": "https://example.invalid?api_key=private"},
        {"exchange_rate_cache_ttl_seconds": 0},
        {"exchange_rate_timeout_seconds": 0},
    ],
)
def test_invalid_config_is_rejected(settings, changes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**settings.model_dump(), **changes})


def test_key_is_masked_in_settings(settings):
    assert "synthetic-exchange-marker" not in repr(settings)
    assert "synthetic-exchange-marker" not in settings.model_dump_json()
