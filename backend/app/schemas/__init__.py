from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class Summary(BaseModel):
    total_revenue: float
    total_orders: int
    total_customers: int
    average_order_value: float
    revenue_growth: float | None
    previous_revenue: float
    start_date: date
    end_date: date


class TrendPoint(BaseModel):
    date: date
    revenue: float
    orders: int


class Category(BaseModel):
    category: str
    revenue: float
    orders: int
    units: int


class TopProduct(BaseModel):
    id: int
    name: str
    category: str
    revenue: float
    units: int


class RecentSale(BaseModel):
    id: int
    customer_name: str
    product_name: str
    category: str
    quantity: int
    total_amount: float
    created_at: datetime


class SalesPage(BaseModel):
    items: list[RecentSale]
    total: int
    limit: int
    offset: int


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
