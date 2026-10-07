from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.events import SaleCreated, SaleDeleted, SaleSnapshot, SaleUpdated, publish
from app.models import Customer, Product, Sale
from app.schemas import CreateSaleRequest


def _snapshot(sale: Sale, product: Product) -> SaleSnapshot:
    return SaleSnapshot(
        id=sale.id, customer_id=sale.customer_id, product_id=sale.product_id,
        product_name=product.name, category=product.category,
        quantity=sale.quantity, total_amount=sale.total_amount,
    )


def customers(db: Session):
    return db.scalars(select(Customer).order_by(Customer.name, Customer.id)).all()


def products(db: Session):
    return db.scalars(select(Product).order_by(Product.name, Product.id)).all()


def create_sale(db: Session, request: CreateSaleRequest) -> Sale:
    if db.get(Customer, request.customer_id) is None:
        raise HTTPException(404, "Customer not found.")
    product = db.get(Product, request.product_id)
    if product is None:
        raise HTTPException(404, "Product not found.")
    total = product.price * request.quantity
    if total > Decimal("999999999999.99"):
        raise HTTPException(422, "Quantity is too large for this product's price.")
    sale = Sale(
        customer_id=request.customer_id,
        product_id=request.product_id,
        quantity=request.quantity,
        total_amount=total,
    )
    try:
        db.add(sale)
        # Capture related values before commit expires ORM objects.
        db.flush()
        snapshot = _snapshot(sale, product)
        db.commit()
        db.refresh(sale)
    except SQLAlchemyError:
        db.rollback()
        raise
    publish(SaleCreated(snapshot))
    return sale


def delete_sale(db: Session, sale_id: int) -> None:
    sale = db.get(Sale, sale_id)
    if sale is None:
        raise HTTPException(404, "Sale not found.")
    snapshot = _snapshot(sale, sale.product)
    try:
        db.delete(sale)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    publish(SaleDeleted(snapshot))


def update_sale(db: Session, sale_id: int, request: CreateSaleRequest) -> Sale:
    sale = db.get(Sale, sale_id)
    if sale is None:
        raise HTTPException(404, "Sale not found.")
    if db.get(Customer, request.customer_id) is None:
        raise HTTPException(404, "Customer not found.")
    product = db.get(Product, request.product_id)
    if product is None:
        raise HTTPException(404, "Product not found.")
    total = product.price * request.quantity
    if total > Decimal("999999999999.99"):
        raise HTTPException(422, "Quantity is too large for this product's price.")
    previous = _snapshot(sale, sale.product)
    try:
        sale.customer_id = request.customer_id
        sale.product_id = request.product_id
        sale.quantity = request.quantity
        sale.total_amount = total
        snapshot = _snapshot(sale, product)
        db.commit()
        db.refresh(sale)
    except SQLAlchemyError:
        db.rollback()
        raise
    publish(SaleUpdated(snapshot, previous))
    return sale
