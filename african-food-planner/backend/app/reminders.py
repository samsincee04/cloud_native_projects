from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import create_tables
from app.models import Reminder, User


ALLOWED_REMINDER_TYPES = frozenset({"expiry", "meal_plan"})


def create_reminder(
    session: Session,
    user_id: UUID,
    type: str,
    title: str,
    body: str,
    due_at: datetime | None,
) -> Reminder:
    """
    Create a Reminder row.

    We call `create_tables()` here to keep worker code simple and avoid Alembic.
    It's idempotent (CREATE TABLE IF NOT EXISTS semantics via SQLAlchemy metadata).
    """
    create_tables()

    if type not in ALLOWED_REMINDER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid reminder type")

    if session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")

    reminder = Reminder(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        due_at=due_at,
        # is_read uses the model default (false)
    )
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return reminder


def list_reminders_for_user(session: Session, user_id: UUID) -> list[Reminder]:
    return (
        session.scalars(
            select(Reminder)
            .where(Reminder.user_id == user_id)
            .order_by(Reminder.created_at.desc())
        )
        .all()
    )

