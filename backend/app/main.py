from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.routers import ai, dashboard, sales
from app.schemas import Health

app = FastAPI(title="AI Sales Analytics API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type"],
)
app.include_router(dashboard.router)
app.include_router(ai.router)
app.include_router(sales.router)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    # Do not expose connection strings, parameters or customer data in errors.
    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None)
    message = str(original).lower()
    detail = "Database unavailable or not initialized. Check DATABASE_URL and run python -m app.seed."
    if sqlstate == "28P01" or "password authentication failed" in message:
        detail = "Database authentication failed. Check the existing PostgreSQL credentials in backend/.env."
    elif sqlstate == "3D000":
        detail = "Configured database does not exist. Create the database specified in DATABASE_URL."
    elif sqlstate == "42P01":
        detail = "Database schema is not initialized. Run python -m app.seed."
    elif isinstance(exc, OperationalError):
        detail = "Database connection unavailable. Start PostgreSQL and check DATABASE_URL in backend/.env."
    return JSONResponse(
        status_code=503,
        content={"detail": detail},
    )


@app.get("/api/health", response_model=Health)
def health(db: Annotated[Session, Depends(get_db)]):
    tables = db.execute(
        text("SELECT to_regclass('customers'), to_regclass('products'), to_regclass('sales')")
    ).one()
    if any(table is None for table in tables):
        raise HTTPException(503, "Database schema is not initialized. Run python -m app.seed.")
    return Health(
        status="ok", database="connected", ai_configured=bool(get_settings().openai_api_key.strip())
    )
