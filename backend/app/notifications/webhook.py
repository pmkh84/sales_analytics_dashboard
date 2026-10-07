"""Register the public demo webhook without exposing the bot token in shell arguments."""

import argparse
import sys
from urllib.parse import urlsplit

from app.config import get_settings
from app.notifications.telegram import TelegramClient, TelegramError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public HTTPS backend URL ending in /api/telegram/webhook")
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme != "https" or not url.netloc:
        parser.error("Use a public HTTPS webhook URL.")
    settings = get_settings()
    token = settings.telegram_bot_token.get_secret_value().strip()
    if not token:
        parser.error("Configure TELEGRAM_BOT_TOKEN in backend/.env first.")
    client = TelegramClient(token, settings.telegram_api_url, settings.telegram_timeout_seconds)
    try:
        client.set_webhook(args.url)
    except TelegramError as exc:
        print(
            f"Webhook registration failed: reason={exc.reason} status_code={exc.status_code}", file=sys.stderr
        )
        raise SystemExit(1) from None
    print("Telegram webhook registered. Send /start to the bot to subscribe.")


if __name__ == "__main__":
    main()
