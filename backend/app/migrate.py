"""Additive, transactional historical pricing migration; no historical backfill."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.database import Base, engine
from app.models import Sale


def migrate_connection(connection: Connection) -> None:
    connection.execute(text("SELECT pg_advisory_xact_lock(7142026)"))
    Base.metadata.create_all(connection)
    connection.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS exchange_rate_toman NUMERIC(20, 6)"))
    connection.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS total_amount_toman NUMERIC(32, 2)"))
    constraints = {item["name"] for item in inspect(connection).get_check_constraints("sales")}
    if "historical_pricing_consistent" not in constraints:
        constraint = next(c for c in Sale.__table__.constraints if c.name == "historical_pricing_consistent")
        connection.execute(
            text(
                f"ALTER TABLE sales ADD CONSTRAINT historical_pricing_consistent CHECK ({constraint.sqltext})"
            )
        )


def migrate() -> None:
    with engine.begin() as connection:
        migrate_connection(connection)
    print("Historical pricing schema ready; existing USD totals preserved, no rates backfilled.")


if __name__ == "__main__":
    migrate()
