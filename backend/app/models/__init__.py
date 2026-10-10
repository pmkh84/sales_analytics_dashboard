from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sales: Mapped[list["Sale"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price >= 0", name="positive_price"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(80), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sales: Mapped[list["Sale"]] = relationship(back_populates="product")


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("total_amount >= 0", name="positive_total"),
        CheckConstraint(
            "(exchange_rate_toman IS NULL AND total_amount_toman IS NULL) OR "
            "(exchange_rate_toman IS NOT NULL AND total_amount_toman IS NOT NULL "
            "AND exchange_rate_toman > 0 AND total_amount_toman >= 0 "
            "AND total_amount_toman = round(total_amount * exchange_rate_toman, 2))",
            name="historical_pricing_consistent",
        ),
        Index("ix_sales_created_id", "created_at", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int]
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    exchange_rate_toman: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    total_amount_toman: Mapped[Decimal | None] = mapped_column(Numeric(32, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    customer: Mapped[Customer] = relationship(back_populates="sales")
    product: Mapped[Product] = relationship(back_populates="sales")


class TelegramSubscriber(Base):
    __tablename__ = "telegram_subscribers"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    chat_type: Mapped[str] = mapped_column(String(32))
    username: Mapped[str | None] = mapped_column(String(256))
    first_name: Mapped[str | None] = mapped_column(String(256))
    last_name: Mapped[str | None] = mapped_column(String(256))
    title: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
