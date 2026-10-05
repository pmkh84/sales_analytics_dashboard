from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
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
        Index("ix_sales_created_id", "created_at", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int]
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    customer: Mapped[Customer] = relationship(back_populates="sales")
    product: Mapped[Product] = relationship(back_populates="sales")
