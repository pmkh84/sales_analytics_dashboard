from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import Category, SalesPage, Summary, TopProduct, TrendPoint
from app.services import analytics

router = APIRouter(prefix="/api", tags=["Analytics"])
Database = Annotated[Session, Depends(get_db)]


def date_range(start_date: date | None = None, end_date: date | None = None):
    return analytics.resolve_period(start_date, end_date)


DateRange = Annotated[analytics.Period, Depends(date_range)]


@router.get("/dashboard/summary", response_model=Summary)
def get_summary(db: Database, period: DateRange):
    return analytics.summary(db, period)


@router.get("/dashboard/revenue-trend", response_model=list[TrendPoint])
def get_trend(db: Database, period: DateRange, interval: Literal["day", "month"] = "day"):
    return analytics.revenue_trend(db, period, interval)


@router.get("/dashboard/categories", response_model=list[Category])
def get_categories(db: Database, period: DateRange):
    return analytics.categories(db, period)


@router.get("/dashboard/top-products", response_model=list[TopProduct])
def get_products(db: Database, period: DateRange, limit: Annotated[int, Query(ge=1, le=30)] = 5):
    return analytics.top_products(db, period, limit)


@router.get("/sales/recent", response_model=SalesPage)
def get_sales(
    db: Database,
    period: DateRange,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
):
    return analytics.recent_sales(db, period, limit, offset)
