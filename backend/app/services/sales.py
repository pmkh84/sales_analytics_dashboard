from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.events import SaleCreated, SaleDeleted, SaleSnapshot, SaleUpdated, publish
from app.models import Customer, Product, Sale
from app.schemas import CreateSaleRequest
from app.services import pricing
from app.services.exchange_rate import get_exchange_rate_service


def _snapshot(sale: Sale, product: Product) -> SaleSnapshot:
    return SaleSnapshot(
        id=sale.id,
        customer_id=sale.customer_id,
        product_id=sale.product_id,
        product_name=product.name,
        category=product.category,
        quantity=sale.quantity,
        total_amount=sale.total_amount,
        exchange_rate_toman=sale.exchange_rate_toman,
        total_amount_toman=sale.total_amount_toman,
    )


def customers(db: Session):
    return db.scalars(select(Customer).order_by(Customer.name, Customer.id)).all()


def products(db: Session):
    items = db.scalars(select(Product).order_by(Product.name, Product.id)).all()
    if not items:
        return []
    try:
        quote = get_exchange_rate_service().get_rate()
        rate, stale = pricing.usable_rate(quote), quote.stale
    except HTTPException:
        rate, stale = None, None
    return [
        {
            "id": item.id,
            "name": item.name,
            "price": item.price,
            "price_usd": item.price,
            "price_toman": pricing.toman_total(item.price, rate) if rate is not None else None,
            "exchange_rate_stale": stale,
        }
        for item in items
    ]


def create_sale(db: Session, request: CreateSaleRequest) -> Sale:
    if db.get(Customer, request.customer_id) is None:
        raise HTTPException(404, "Customer not found.")
    product = db.get(Product, request.product_id)
    if product is None:
        raise HTTPException(404, "Product not found.")
    total, rate, total_toman = pricing.sale_prices(product.price, request.quantity)
    sale = Sale(
        customer_id=request.customer_id,
        product_id=request.product_id,
        quantity=request.quantity,
        total_amount=total,
        exchange_rate_toman=rate,
        total_amount_toman=total_toman,
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
    # Non-financial edits preserve saved values, including null legacy amounts.
    reprice = sale.product_id != request.product_id or sale.quantity != request.quantity
    prices = pricing.sale_prices(product.price, request.quantity) if reprice else None
    previous = _snapshot(sale, sale.product)
    try:
        sale.customer_id = request.customer_id
        sale.product_id = request.product_id
        sale.quantity = request.quantity
        if prices is not None:
            sale.total_amount, sale.exchange_rate_toman, sale.total_amount_toman = prices
        snapshot = _snapshot(sale, product)
        db.commit()
        db.refresh(sale)
    except SQLAlchemyError:
        db.rollback()
        raise
    publish(SaleUpdated(snapshot, previous))
    return sale
