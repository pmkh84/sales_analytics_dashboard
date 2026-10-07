"""Open demo subscriptions: persist commands before sending confirmations."""

from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import TelegramSubscriber
from app.notifications import service


class TelegramChat(BaseModel):
    id: int = Field(strict=True, ge=-(2**63), le=2**63 - 1)
    type: str = Field(max_length=32)
    username: str | None = Field(default=None, max_length=256)
    first_name: str | None = Field(default=None, max_length=256)
    last_name: str | None = Field(default=None, max_length=256)
    title: str | None = Field(default=None, max_length=256)


class TelegramMessage(BaseModel):
    chat: TelegramChat
    text: str | None = None


class TelegramUpdate(BaseModel):
    update_id: int = Field(strict=True)
    message: TelegramMessage | None = None


def handle_update(db: Session, incoming: TelegramUpdate) -> None:
    message = incoming.message
    if message is None or not message.text:
        return
    # Arguments are optional and ignored; no invitation code or approval is needed.
    words = message.text.split()
    if not words:
        return
    command = words[0].split("@", 1)[0]
    if command not in {"/start", "/stop"}:
        return
    chat = message.chat
    active = command == "/start"
    try:
        if active:
            metadata = chat.model_dump(exclude={"id", "type"}, exclude_none=True)
            values = {"chat_type": chat.type, "is_active": True, **metadata}
            statement = insert(TelegramSubscriber).values(chat_id=chat.id, **values)
            db.execute(
                statement.on_conflict_do_update(
                    index_elements=[TelegramSubscriber.chat_id],
                    set_={**values, "updated_at": func.now()},
                )
            )
        else:
            db.execute(
                update(TelegramSubscriber)
                .where(TelegramSubscriber.chat_id == chat.id)
                .values(
                    is_active=False,
                    updated_at=func.now(),
                )
            )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    handler = service.get_notification_handler()
    if handler is not None:
        handler.confirm_subscription(chat.id, active)


def active_chat_ids(db: Session | None = None) -> list[int]:
    statement = (
        select(TelegramSubscriber.chat_id)
        .where(
            TelegramSubscriber.is_active.is_(True),
        )
        .order_by(TelegramSubscriber.chat_id)
    )
    if db is not None:
        return list(db.scalars(statement))
    with SessionLocal() as session:
        return list(session.scalars(statement))
