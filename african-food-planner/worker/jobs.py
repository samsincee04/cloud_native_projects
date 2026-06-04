"""Scheduled worker jobs; MVP persists results as user notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import MealPlan, Notification, PantryItem, User
from app.shopping_list import regenerate_shopping_list


@dataclass(frozen=True)
class JobReport:
    created_count: int = 0
    skipped_count: int = 0

    def add(self, created: int = 0, skipped: int = 0) -> "JobReport":
        return JobReport(
            created_count=self.created_count + created,
            skipped_count=self.skipped_count + skipped,
        )


def _notification_exists_today(
    session: Session,
    *,
    user_id: UUID,
    type: str,
    title: str,
) -> bool:
    today = datetime.now(timezone.utc).date()
    return (
        session.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.type == type,
                Notification.title == title,
                func.date(Notification.created_at) == today,
            )
        )
        is not None
    )


def _create_notification_if_new(
    session: Session,
    *,
    user_id: UUID,
    type: str,
    title: str,
    body: str,
    metadata_json: dict | None = None,
) -> bool:
    if _notification_exists_today(
        session, user_id=user_id, type=type, title=title
    ):
        return False
    session.add(
        Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            metadata_json=metadata_json,
        )
    )
    return True


def _next_monday_utc(now: datetime) -> datetime:
    today = now.date()
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    next_mon = today + timedelta(days=days_ahead)
    return datetime.combine(next_mon, time.min, tzinfo=timezone.utc)


def run_expiry_alerts(session: Session) -> JobReport:
    """Notify users about pantry items expiring within three days."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=3)

    items = session.scalars(
        select(PantryItem).where(
            PantryItem.expires_at.is_not(None),
            PantryItem.expires_at <= cutoff,
        )
    ).all()

    created = 0
    skipped = 0
    for item in items:
        due_at = item.expires_at
        assert due_at is not None
        title = f"Expiring soon: {item.ingredient_name} ({item.unit})"
        body = (
            f"You have {item.quantity} {item.unit} of {item.ingredient_name} "
            f"expiring on {due_at.date().isoformat()}."
        )
        if _create_notification_if_new(
            session,
            user_id=item.user_id,
            type="expiry_alert",
            title=title,
            body=body,
            metadata_json={
                "pantry_item_id": str(item.id),
                "expires_at": due_at.isoformat(),
            },
        ):
            created += 1
        else:
            skipped += 1

    session.commit()
    return JobReport(created_count=created, skipped_count=skipped)


def run_weekly_plan_reminder(session: Session) -> JobReport:
    """Remind users to plan (or confirm) meals for the upcoming week."""
    now = datetime.now(timezone.utc)
    next_monday = _next_monday_utc(now)
    week_start_date = next_monday.date()

    user_ids = session.scalars(select(User.id)).all()
    plan_user_ids = set(
        session.scalars(
            select(MealPlan.user_id).where(
                MealPlan.week_start_date == week_start_date
            )
        ).all()
    )

    created = 0
    skipped = 0
    for user_id in user_ids:
        has_plan = user_id in plan_user_ids
        title = (
            "Meal plan ready for next week"
            if has_plan
            else "Plan your week"
        )
        body = (
            f"Week starting {week_start_date.isoformat()}: "
            + (
                "your meal plan is set."
                if has_plan
                else "create a meal plan when you can."
            )
        )
        if _create_notification_if_new(
            session,
            user_id=user_id,
            type="weekly_plan_reminder",
            title=title,
            body=body,
            metadata_json={"week_start_date": week_start_date.isoformat()},
        ):
            created += 1
        else:
            skipped += 1

    session.commit()
    return JobReport(created_count=created, skipped_count=skipped)


def run_refresh_shopping_lists(session: Session) -> JobReport:
    """Regenerate shopping lists for meal plans that have scheduled meals."""
    plans = session.scalars(
        select(MealPlan).options(selectinload(MealPlan.items))
    ).all()

    created = 0
    skipped = 0
    for plan in plans:
        if not plan.items:
            skipped += 1
            continue

        regenerate_shopping_list(session, plan.id)
        item_count = len(plan.items)
        title = f"Shopping list updated: week {plan.week_start_date.isoformat()}"
        body = (
            f"Regenerated your shopping list from {item_count} planned meal(s) "
            f"for the week of {plan.week_start_date.isoformat()}."
        )
        if _create_notification_if_new(
            session,
            user_id=plan.user_id,
            type="shopping_list_refresh",
            title=title,
            body=body,
            metadata_json={
                "meal_plan_id": str(plan.id),
                "week_start_date": plan.week_start_date.isoformat(),
            },
        ):
            created += 1
        else:
            skipped += 1

    session.commit()
    return JobReport(created_count=created, skipped_count=skipped)
