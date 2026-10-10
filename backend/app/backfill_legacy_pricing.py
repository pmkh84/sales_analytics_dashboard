"""Backfill unpriced legacy sales at the user-approved fixed USD/Toman rate."""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.database import engine
from app.migrate import migrate_connection

# User-approved conversion for legacy sales, not a quote from the rate provider.
LEGACY_EXCHANGE_RATE_TOMAN = Decimal("267000.000000")


def backfill_connection(connection: Connection) -> int:
    """Fill missing prices atomically; preserve USD totals and previously priced sales."""
    connection.execute(text("SELECT pg_advisory_xact_lock(7142026)"))
    result = connection.execute(
        text(
            "UPDATE sales "
            "SET exchange_rate_toman = :rate, "
            "total_amount_toman = round(total_amount * :rate, 2) "
            "WHERE exchange_rate_toman IS NULL AND total_amount_toman IS NULL"
        ),
        {"rate": LEGACY_EXCHANGE_RATE_TOMAN},
    )
    return result.rowcount


def backfill() -> int:
    with engine.begin() as connection:
        migrate_connection(connection)
        updated = backfill_connection(connection)
    print(f"Priced {updated} legacy sales at {LEGACY_EXCHANGE_RATE_TOMAN:,.0f} Toman per USD.")
    return updated


if __name__ == "__main__":
    backfill()
