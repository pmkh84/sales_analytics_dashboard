from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models import Customer, Product, Sale


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @property
    def bounds(self):
        return (
            datetime.combine(self.start, time.min, timezone.utc),
            datetime.combine(self.end + timedelta(days=1), time.min, timezone.utc),
        )

    @property
    def previous(self):
        length = (self.end - self.start).days + 1
        return Period(self.start - timedelta(days=length), self.start - timedelta(days=1))


def resolve_period(start_date: date | None = None, end_date: date | None = None) -> Period:
    end = end_date or datetime.now(timezone.utc).date()
    if end < date(1900, 1, 1) or end > date(9998, 12, 31):
        raise HTTPException(422, "Date range is outside supported bounds.")
    start = start_date or end - timedelta(days=29)
    if start > end:
        raise HTTPException(422, "start_date must be on or before end_date.")
    if (end - start).days > 730:
        raise HTTPException(422, "Choose a date range of at most 731 days.")
    if start < date(1900, 1, 1):
        raise HTTPException(422, "Date range is outside supported bounds.")
    return Period(start, end)


def conditions(period: Period):
    start, end = period.bounds
    return Sale.created_at >= start, Sale.created_at < end


def summary(db: Session, period: Period) -> dict:
    revenue, orders, customers = db.execute(
        select(
            func.coalesce(func.sum(Sale.total_amount), 0),
            func.count(Sale.id),
            func.count(distinct(Sale.customer_id)),
        ).where(*conditions(period))
    ).one()
    previous = db.scalar(
        select(func.coalesce(func.sum(Sale.total_amount), 0)).where(*conditions(period.previous))
    )
    return {
        "total_revenue": float(revenue),
        "total_orders": orders,
        "total_customers": customers,
        "average_order_value": float(round(revenue / orders, 2)) if orders else 0,
        "revenue_growth": float(round((revenue - previous) / previous * 100, 2)) if previous else None,
        "previous_revenue": float(previous),
        "start_date": period.start,
        "end_date": period.end,
    }


def revenue_trend(db: Session, period: Period, interval: str = "day") -> list[dict]:
    bucket = func.date_trunc(interval, Sale.created_at)
    rows = db.execute(
        select(bucket, func.sum(Sale.total_amount), func.count(Sale.id))
        .where(*conditions(period))
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    values = {row[0].date(): (float(row[1]), row[2]) for row in rows}
    cursor = period.start if interval == "day" else period.start.replace(day=1)
    result = []
    while cursor <= period.end:
        revenue, orders = values.get(cursor, (0, 0))
        result.append({"date": cursor, "revenue": revenue, "orders": orders})
        if interval == "day":
            cursor += timedelta(days=1)
        else:
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result


def categories(db: Session, period: Period) -> list[dict]:
    rows = db.execute(
        select(
            Product.category,
            func.sum(Sale.total_amount).label("revenue"),
            func.count(Sale.id),
            func.sum(Sale.quantity),
        )
        .join(Product, Sale.product_id == Product.id)
        .where(*conditions(period))
        .group_by(Product.category)
        .order_by(func.sum(Sale.total_amount).desc(), Product.category)
    )
    return [{"category": r[0], "revenue": float(r[1]), "orders": r[2], "units": r[3]} for r in rows]


def top_products(db: Session, period: Period, limit: int = 5) -> list[dict]:
    rows = db.execute(
        select(
            Product.id, Product.name, Product.category, func.sum(Sale.total_amount), func.sum(Sale.quantity)
        )
        .join(Product, Sale.product_id == Product.id)
        .where(*conditions(period))
        .group_by(Product.id)
        .order_by(func.sum(Sale.total_amount).desc(), Product.id)
        .limit(limit)
    )
    return [{"id": r[0], "name": r[1], "category": r[2], "revenue": float(r[3]), "units": r[4]} for r in rows]


def recent_sales(db: Session, period: Period, limit: int, offset: int) -> dict:
    rows = db.execute(
        select(Sale, Customer.name, Product.name, Product.category)
        .join(Customer, Sale.customer_id == Customer.id)
        .join(Product, Sale.product_id == Product.id)
        .where(*conditions(period))
        .order_by(Sale.created_at.desc(), Sale.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        {
            "id": sale.id,
            "customer_id": sale.customer_id,
            "product_id": sale.product_id,
            "customer_name": customer,
            "product_name": product,
            "category": category,
            "quantity": sale.quantity,
            "total_amount": float(sale.total_amount),
            "created_at": sale.created_at,
        }
        for sale, customer, product, category in rows
    ]
    total = db.scalar(select(func.count(Sale.id)).where(*conditions(period)))
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def analytics_context(db: Session, period: Period) -> dict:
    # Aggregate-only payload: no transaction records, customer names or emails.
    return {
        "currency": "USD",
        "timezone": "UTC",
        "definitions": {
            "orders": "Each sale record is one single-product order.",
            "customers": "Distinct purchasing customers in the selected period.",
            "growth": "Revenue compared with the immediately preceding equal-length period.",
            "limitations": "No cost, profit, marketing, inventory, or causal attribution data.",
        },
        "selected_period": summary(db, period),
        "previous_period": summary(db, period.previous),
        "categories": categories(db, period),
        "previous_categories": categories(db, period.previous),
        "top_products_by_revenue": top_products(db, period),
        "monthly_trend": revenue_trend(db, period, "month"),
    }
