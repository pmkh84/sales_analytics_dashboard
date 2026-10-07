"""Telegram webhook transport; subscription behavior lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.notifications.subscriptions import TelegramUpdate, handle_update

router = APIRouter(prefix="/api/telegram", tags=["Telegram"])


@router.post("/webhook")
def webhook(incoming: TelegramUpdate, db: Annotated[Session, Depends(get_db)]):
    handle_update(db, incoming)
    return {"ok": True}
