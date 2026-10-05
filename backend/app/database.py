from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5, "options": "-c timezone=UTC -c statement_timeout=15000"},
)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    with SessionLocal() as session:
        yield session
