"""Transactional outbox: business data and pending events commit together."""
from datetime import datetime, timezone
from sqlalchemy import String, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base, new_id


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    topic: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Inbox(Base):
    __tablename__ = "evento_processado"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)


def emit(session, topic, payload):
    event_id = new_id()
    session.add(Outbox(id=event_id, topic=topic, payload={**payload, "evento_id": event_id}))
    return event_id
