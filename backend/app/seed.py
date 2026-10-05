"""Initialize PostgreSQL tables and add deterministic demo data only to an empty database."""

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, text

from app.database import Base, SessionLocal, engine
from app.models import Customer, Product, Sale

CATALOG = {
    "Electronics": [
        ("Studio Headphones", 149),
        ("Wireless Keyboard", 89),
        ("4K Webcam", 119),
        ("Portable Speaker", 79),
        ("USB-C Dock", 129),
        ("Smart Monitor", 329),
    ],
    "Home & Living": [
        ("Desk Lamp", 49),
        ("Linen Throw", 69),
        ("Ceramic Planter", 29),
        ("Pour-over Set", 59),
        ("Wall Clock", 39),
        ("Storage Basket", 24),
    ],
    "Fashion": [
        ("Everyday Backpack", 79),
        ("Cotton Tee", 29),
        ("Canvas Sneakers", 69),
        ("Wool Beanie", 25),
        ("Linen Shirt", 59),
        ("Crossbody Bag", 49),
    ],
    "Sports": [
        ("Yoga Mat", 39),
        ("Running Bottle", 22),
        ("Resistance Bands", 29),
        ("Training Shorts", 35),
        ("Foam Roller", 32),
        ("Trail Pack", 89),
    ],
    "Office": [
        ("Weekly Planner", 19),
        ("Desk Organizer", 29),
        ("Notebook Set", 15),
        ("Laptop Stand", 49),
        ("Ergonomic Chair", 249),
        ("Fountain Pen", 39),
    ],
}
FIRST = ["Alex", "Jordan", "Morgan", "Sam", "Taylor", "Casey", "Riley", "Avery", "Jamie", "Cameron"]
LAST = ["Chen", "Patel", "Smith", "Garcia", "Kim", "Wilson", "Brown", "Davis", "Ali", "Martin"]


def seed():
    Base.metadata.create_all(engine)
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=210)).replace(hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(7142026)"))
        if any(db.scalar(select(func.count()).select_from(model)) for model in (Customer, Product, Sale)):
            print("Database already contains data; nothing changed.")
            return
        customers = [
            Customer(
                name=f"{first} {last}",
                email=f"customer{i + 1}@example.com",
                created_at=start - timedelta(days=rng.randint(1, 120)),
            )
            for i, (first, last) in enumerate((first, last) for first in FIRST for last in LAST)
        ]
        products = [
            Product(name=name, category=category, price=Decimal(price))
            for category, entries in CATALOG.items()
            for name, price in entries
        ]
        db.add_all(customers + products)
        db.flush()
        sales = []
        weights = [3 if product.category == "Electronics" else 1 for product in products]
        for _ in range(1500):
            product = rng.choices(products, weights=weights)[0]
            # Increasing activity over seven months; no future transactions.
            fraction = rng.random() ** 0.75
            when = start + (now - start) * fraction
            quantity = rng.choices([1, 2, 3, 4], weights=[65, 23, 9, 3])[0]
            discount = rng.choice([Decimal("1"), Decimal("1"), Decimal("0.9")])
            sales.append(
                Sale(
                    customer_id=rng.choice(customers).id,
                    product_id=product.id,
                    quantity=quantity,
                    total_amount=(product.price * quantity * discount).quantize(Decimal("0.01")),
                    created_at=when,
                )
            )
        db.add_all(sales)
    print("Seeded 100 customers, 30 products, and 1,500 sales across seven months.")


if __name__ == "__main__":
    seed()
