from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
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
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database unavailable or not initialized. Check DATABASE_URL and run python -m app.seed."
        },
    )


@app.get("/api/health", response_model=Health)
def health(db: Annotated[Session, Depends(get_db)]):
    db.execute(text("SELECT 1"))
    return Health(
        status="ok", database="connected", ai_configured=bool(get_settings().openai_api_key.strip())
    )
