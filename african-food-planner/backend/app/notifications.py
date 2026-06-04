from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Notification
from app.pantry import require_user
from app.schemas import NotificationResponse


def notification_response(notification: Notification) -> NotificationResponse:
    return NotificationResponse.model_validate(notification)


def list_notifications_for_user(
    session: Session, user_id: UUID, *, limit: int = 50
) -> list[NotificationResponse]:
    require_user(session, user_id)
    rows = session.scalars(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    ).all()
    return [notification_response(n) for n in rows]


def mark_notification_read(
    session: Session, notification_id: UUID
) -> NotificationResponse:
    notification = session.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)

    return notification_response(notification)


def mark_all_notifications_read(session: Session, user_id: UUID) -> int:
    require_user(session, user_id)
    now = datetime.now(timezone.utc)
    result = session.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    return int(result.rowcount or 0)
