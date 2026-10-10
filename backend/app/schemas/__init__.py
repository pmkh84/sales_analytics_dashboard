from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Summary(BaseModel):
    total_revenue: Decimal
    total_orders: int
    total_customers: int
    average_order_value: Decimal
    revenue_growth: float | None
    previous_revenue: Decimal
    currency: Literal["IRT"] = "IRT"
    priced_orders: int
    legacy_orders: int
    previous_legacy_orders: int
    start_date: date
    end_date: date


class TrendPoint(BaseModel):
    date: date
    revenue: Decimal
    orders: int


class Category(BaseModel):
    category: str
    revenue: Decimal
    orders: int
    units: int


class TopProduct(BaseModel):
    id: int
    name: str
    category: str
    revenue: Decimal
    units: int


class RecentSale(BaseModel):
    id: int
    customer_id: int
    product_id: int
    customer_name: str
    product_name: str
    category: str
    quantity: int
    total_amount: Decimal  # Compatibility: USD, never Toman.
    exchange_rate_toman: Decimal | None
    total_amount_toman: Decimal | None
    created_at: datetime


class SalesPage(BaseModel):
    items: list[RecentSale]
    total: int
    limit: int
    offset: int


class CreateSaleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int = Field(strict=True, gt=0, le=2147483647)
    product_id: int = Field(strict=True, gt=0, le=2147483647)
    quantity: int = Field(strict=True, gt=0, le=2147483647)


class CreatedSale(CreateSaleRequest):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total_amount: Decimal
    exchange_rate_toman: Decimal | None
    total_amount_toman: Decimal | None
    created_at: datetime


class CustomerOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class ProductOption(CustomerOption):
    price: Decimal  # Compatibility: USD.
    price_usd: Decimal
    price_toman: Decimal | None
    exchange_rate_stale: bool | None


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000, pattern=r".*\S.*")


class Answer(BaseModel):
    answer: str


class Insight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    detail: str


class Insights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    insights: list[Insight] = Field(min_length=3, max_length=5)


class Health(BaseModel):
    status: str
    database: str
    ai_configured: bool


class ExchangeRate(BaseModel):
    model_config = ConfigDict(frozen=True)
    base: Literal["USD"] = "USD"
    quote: Literal["IRT"] = "IRT"
    rate: Decimal = Field(gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    updated_at: datetime
    source: Literal["Navasan"] = "Navasan"
    stale: bool = False
