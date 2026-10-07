"""Notification unit tests: all HTTP calls use an in-memory transport."""

import json
import logging
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock, call

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.events import SaleCreated, SaleDeleted, SaleSnapshot, SaleUpdated, publish
from app.notifications import service, telegram, webhook
from app.notifications.service import NotificationHandler, format_message
from app.notifications.telegram import TelegramClient, TelegramError


@pytest.fixture(autouse=True)
def isolated_telegram_settings(monkeypatch):
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_ENABLED",
        "TELEGRAM_API_URL",
        "TELEGRAM_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    cached_handler = service.get_notification_handler
    cached_handler.cache_clear()
    yield
    cached_handler.cache_clear()


@pytest.fixture
def snapshot():
    return SaleSnapshot(123, 7, 9, "Laptop", "Electronics", 2, Decimal("1200.00"))


@pytest.fixture
def mock_http(monkeypatch):
    original_client = httpx.Client

    def install(handler):
        factory = Mock(
            side_effect=lambda **kwargs: original_client(
                **kwargs,
                transport=httpx.MockTransport(handler),
                trust_env=False,
            )
        )
        monkeypatch.setattr(telegram.httpx, "Client", factory)
        return factory

    return install


def test_created_message_and_sold_semantics(snapshot):
    assert format_message(SaleCreated(snapshot)) == (
        "\U0001f7e2 Sale Created (Sold)\n\nSale ID: #123\nCustomer ID: #7\n"
        "Product: Laptop (#9)\nCategory: Electronics\nQuantity: 2\nTotal (USD): 1200.00"
    )


def test_deleted_message_retains_pre_delete_details(snapshot):
    message = format_message(SaleDeleted(snapshot))
    assert message.startswith("\U0001f5d1 Sale Deleted\n\nSale ID: #123")
    assert "Product: Laptop (#9)" in message
    assert "Total (USD): 1200.00" in message


def test_updated_message_only_lists_changed_fields(snapshot):
    current = replace(
        snapshot,
        customer_id=8,
        product_id=10,
        product_name="Book",
        category="Books",
        quantity=3,
        total_amount=Decimal("1100"),
    )
    message = format_message(SaleUpdated(current, snapshot))
    assert message == (
        "\u270f\ufe0f Sale Updated\n\nSale ID: #123\n\nChanged fields:\n"
        "Customer ID: #7 \u2192 #8\nProduct: Laptop (#9) \u2192 Book (#10)\n"
        "Category: Electronics \u2192 Books\nQuantity: 2 \u2192 3\nTotal (USD): 1200.00 \u2192 1100.00"
    )
    message = format_message(SaleUpdated(replace(snapshot, quantity=3), snapshot))
    assert "Quantity: 2 \u2192 3" in message
    assert "Product:" not in message and "Total (USD):" not in message


def test_unchanged_update_has_clear_message(snapshot):
    assert format_message(SaleUpdated(snapshot, snapshot)).endswith("No business values changed.")


def test_untrusted_names_are_plain_text_bounded_and_single_line(snapshot):
    current = replace(
        snapshot, product_name="<b>item</b>\nStatus: forged " + "x" * 500, category="Books\r\n\tOther"
    )
    message = format_message(SaleUpdated(current, snapshot))
    assert "\nStatus: forged" not in message
    assert "<b>item</b>" in message
    assert "Books Other" in message
    assert len(message.encode("utf-16-le")) // 2 < 4096
    assert not hasattr(snapshot, "email")


def test_send_message_payload_success_timeout_and_log_redaction(mock_http, caplog):
    # A synthetic marker, never a real bot credential.
    token = "synthetic-credential-marker"
    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    factory = mock_http(respond)
    client = TelegramClient(token, "https://telegram.example.invalid/proxy/", 1.25)
    with caplog.at_level(logging.DEBUG):
        client.send_message("<b>Plain text</b>", "synthetic-chat")
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == f"/proxy/bot{token}/sendMessage"
    assert json.loads(request.content) == {
        "chat_id": "synthetic-chat",
        "text": "<b>Plain text</b>",
        "link_preview_options": {"is_disabled": True},
    }
    assert factory.call_args.kwargs == {"timeout": 1.25, "follow_redirects": False}
    assert token not in caplog.text
    assert "bot[REDACTED]/sendMessage" in caplog.text


@pytest.mark.parametrize(
    "status,body,reason",
    [
        (401, {"ok": False, "description": "private response"}, "http_status"),
        (429, {"ok": False, "parameters": {"retry_after": 30}}, "http_status"),
        (500, {"ok": False}, "http_status"),
        (302, {}, "http_status"),
        (200, {"ok": False, "description": "private response"}, "api_rejected"),
        (200, [], "api_rejected"),
        (200, {}, "api_rejected"),
    ],
)
def test_http_and_api_failures_are_sanitized(mock_http, status, body, reason):
    mock_http(lambda request: httpx.Response(status, json=body))
    with pytest.raises(TelegramError) as caught:
        TelegramClient("synthetic-marker", "https://example.invalid", 1).send_message(
            "Sale", "synthetic-chat"
        )
    assert caught.value.reason == reason
    assert caught.value.status_code == (status if reason == "http_status" else None)
    assert "private" not in str(caught.value)
    assert "synthetic" not in str(caught.value)


def test_invalid_json_response(mock_http):
    mock_http(lambda request: httpx.Response(200, text="private invalid body"))
    with pytest.raises(TelegramError, match="invalid_response"):
        TelegramClient("synthetic-marker", "https://example.invalid", 1).send_message(
            "Sale", "synthetic-chat"
        )


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_network_errors_are_sanitized(mock_http, error):
    def fail(request):
        raise error("private URL and credential", request=request)

    mock_http(fail)
    with pytest.raises(TelegramError, match="transport_error") as caught:
        TelegramClient("synthetic-marker", "https://example.invalid", 1).send_message(
            "Sale", "synthetic-chat"
        )
    assert caught.value.__suppress_context__
    assert "private" not in str(caught.value)


def test_handler_logs_safe_failure_context(snapshot, caplog):
    client = Mock()
    client.send_message.side_effect = TelegramError("http_status", 429)
    NotificationHandler(client, lambda: [7]).handle(SaleCreated(snapshot))
    assert "event=SaleCreated sale_id=123 reason=http_status status_code=429" in caplog.text


def test_unexpected_handler_failure_cannot_escape_publisher(snapshot, monkeypatch, caplog):
    handler = Mock()
    handler.handle.side_effect = RuntimeError("private credentials and customer data")
    monkeypatch.setattr(service, "get_notification_handler", lambda: handler)
    publish(SaleCreated(snapshot))
    assert "event=SaleCreated sale_id=123 error_type=RuntimeError" in caplog.text
    assert "private" not in caplog.text


@pytest.mark.parametrize(
    "enabled,token,expected",
    [
        (True, "", "configure TELEGRAM_BOT_TOKEN"),
        (True, "  ", "configure TELEGRAM_BOT_TOKEN"),
        (False, "synthetic-marker", "disabled by TELEGRAM_ENABLED"),
    ],
)
def test_optional_config_disables_without_http(monkeypatch, caplog, enabled, token, expected):
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        telegram_enabled=enabled,
        telegram_bot_token=SecretStr(token),
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    factory = Mock()
    monkeypatch.setattr(service, "TelegramClient", factory)
    service.get_notification_handler.cache_clear()
    try:
        with caplog.at_level(logging.INFO):
            assert service.get_notification_handler() is None
            assert service.get_notification_handler() is None
        factory.assert_not_called()
        assert expected in caplog.text
        assert len(caplog.records) == 1
        assert "synthetic-marker" not in caplog.text
    finally:
        service.get_notification_handler.cache_clear()


def test_configured_handler_uses_settings_and_masks_secrets(monkeypatch):
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        telegram_bot_token=SecretStr("synthetic-marker"),
        telegram_api_url="https://example.invalid/proxy/",
        telegram_timeout_seconds=2,
    )
    assert "synthetic-marker" not in repr(settings)
    assert "synthetic-marker" not in settings.model_dump_json()
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    factory = Mock()
    monkeypatch.setattr(service, "TelegramClient", factory)
    service.get_notification_handler.cache_clear()
    try:
        assert isinstance(service.get_notification_handler(), NotificationHandler)
        factory.assert_called_once_with("synthetic-marker", "https://example.invalid/proxy", 2)
    finally:
        service.get_notification_handler.cache_clear()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid",
        "https://user:password@example.invalid",
        "https://example.invalid?key=value",
        "https://example.invalid/#fragment",
        "not-a-url",
    ],
)
def test_invalid_api_configuration(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql+psycopg://localhost/test", telegram_api_url=url)


@pytest.mark.parametrize("timeout", [0, -1, 31, float("nan"), float("inf")])
def test_invalid_timeout_configuration(timeout):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://localhost/test",
            telegram_timeout_seconds=timeout,
        )


def test_settings_validation_errors_do_not_print_credentials():
    with pytest.raises(ValidationError) as caught:
        Settings(
            _env_file=None,
            database_url="sqlite://",
            telegram_bot_token="synthetic-marker",
            telegram_timeout_seconds=0,
        )
    assert "synthetic-marker" not in str(caught.value)


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic-marker")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "synthetic-chat")
    monkeypatch.setenv("TELEGRAM_API_URL", "https://example.invalid/proxy/")
    monkeypatch.setenv("TELEGRAM_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://localhost/test")
    assert settings.telegram_bot_token.get_secret_value() == "synthetic-marker"
    assert not hasattr(settings, "telegram_chat_id")
    assert settings.telegram_api_url == "https://example.invalid/proxy"
    assert settings.telegram_timeout_seconds == 2.5
    assert settings.telegram_enabled is False


def test_no_active_subscribers_means_no_delivery(snapshot):
    client = Mock()
    NotificationHandler(client, lambda: []).handle(SaleCreated(snapshot))
    client.send_message.assert_not_called()


@pytest.mark.parametrize("failure", [TelegramError("http_status", 403), RuntimeError("private data")])
def test_failed_subscriber_does_not_prevent_other_deliveries(snapshot, caplog, failure):
    client = Mock()
    client.send_message.side_effect = [failure, None]
    event = SaleCreated(snapshot)
    NotificationHandler(client, lambda: [7, 8]).handle(event)
    assert client.send_message.call_args_list == [
        call(format_message(event), 7),
        call(format_message(event), 8),
    ]
    assert "private data" not in caplog.text
    assert "event=SaleCreated sale_id=123" in caplog.text


@pytest.mark.parametrize(
    "active,expected",
    [
        (True, "Subscribed! You will receive sale notifications. Send /stop to unsubscribe."),
        (False, "Unsubscribed. Send /start to subscribe again."),
    ],
)
def test_subscription_confirmation(active, expected):
    client = Mock()
    NotificationHandler(client).confirm_subscription(9000000001, active)
    client.send_message.assert_called_once_with(expected, 9000000001)


def test_set_webhook_payload_is_open_and_receives_messages(mock_http):
    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    mock_http(respond)
    client = TelegramClient("synthetic-marker", "https://example.invalid", 1)
    client.set_webhook("https://dashboard.example.invalid/api/telegram/webhook")
    assert captured[0].url.path.endswith("/setWebhook")
    assert json.loads(captured[0].content) == {
        "url": "https://dashboard.example.invalid/api/telegram/webhook",
        "allowed_updates": ["message"],
        "max_connections": 1,
    }


@pytest.mark.parametrize("failure", [False, True])
def test_webhook_registration_command_uses_backend_settings(monkeypatch, capsys, failure):
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        telegram_bot_token="synthetic-marker",
    )
    monkeypatch.setattr(webhook, "get_settings", lambda: settings)
    factory = Mock()
    if failure:
        factory.return_value.set_webhook.side_effect = TelegramError("http_status", 401)
    monkeypatch.setattr(webhook, "TelegramClient", factory)
    url = "https://dashboard.example.invalid/api/telegram/webhook"
    monkeypatch.setattr("sys.argv", ["webhook", url])
    if failure:
        with pytest.raises(SystemExit) as caught:
            webhook.main()
        assert caught.value.code == 1
    else:
        webhook.main()
    factory.return_value.set_webhook.assert_called_once_with(url)
    output = capsys.readouterr()
    assert "synthetic-marker" not in output.out + output.err
    assert "status_code=401" in output.err if failure else "webhook registered" in output.out


def test_webhook_registration_requires_configured_bot_token(monkeypatch):
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://localhost/test")
    monkeypatch.setattr(webhook, "get_settings", lambda: settings)
    factory = Mock()
    monkeypatch.setattr(webhook, "TelegramClient", factory)
    monkeypatch.setattr("sys.argv", ["webhook", "https://example.invalid/api/telegram/webhook"])
    with pytest.raises(SystemExit) as caught:
        webhook.main()
    assert caught.value.code == 2
    factory.assert_not_called()
