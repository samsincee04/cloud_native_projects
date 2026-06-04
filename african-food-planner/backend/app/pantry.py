from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PantryEvent, PantryItem, User
from app.normalize import normalize_ingredient_name, normalize_unit
from app.schemas import PantryEventResponse, PantryItemResponse


def require_user(session: Session, user_id: UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def normalize_pantry_fields(ingredient_name: str, unit: str) -> tuple[str, str]:
    try:
        return normalize_ingredient_name(ingredient_name), normalize_unit(unit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def pantry_item_response(item: PantryItem) -> PantryItemResponse:
    row = PantryItemResponse.model_validate(item)
    return row.model_copy(
        update={"ingredient_name": normalize_ingredient_name(item.ingredient_name)}
    )


def pantry_event_response(event: PantryEvent) -> PantryEventResponse:
    row = PantryEventResponse.model_validate(event)
    return row.model_copy(
        update={"ingredient_name": normalize_ingredient_name(event.ingredient_name)}
    )


def get_pantry_item_or_404(session: Session, item_id: UUID) -> PantryItem:
    item = session.get(PantryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Pantry item not found")
    return item


def find_pantry_item(
    session: Session,
    user_id: UUID,
    ingredient_name: str,
    unit: str,
) -> PantryItem | None:
    return session.scalar(
        select(PantryItem).where(
            PantryItem.user_id == user_id,
            PantryItem.ingredient_name == ingredient_name,
            PantryItem.unit == unit,
        )
    )


def record_event(
    session: Session,
    *,
    user_id: UUID,
    ingredient_name: str,
    delta: float,
    unit: str,
    reason: str,
) -> PantryEvent:
    event = PantryEvent(
        user_id=user_id,
        ingredient_name=ingredient_name,
        delta=delta,
        unit=unit,
        reason=reason,
    )
    session.add(event)
    return event


def upsert_pantry_item(
    session: Session,
    *,
    user_id: UUID,
    ingredient_name: str,
    unit: str,
    quantity_delta: float,
    expires_at=None,
    set_quantity: float | None = None,
) -> PantryItem:
    item = find_pantry_item(session, user_id, ingredient_name, unit)

    if item is None:
        qty = max(0.0, set_quantity if set_quantity is not None else quantity_delta)
        item = PantryItem(
            user_id=user_id,
            ingredient_name=ingredient_name,
            unit=unit,
            quantity=qty,
            expires_at=expires_at,
        )
        session.add(item)
        session.flush()
        return item

    if set_quantity is not None:
        item.quantity = max(0.0, set_quantity)
    else:
        item.quantity = max(0.0, item.quantity + quantity_delta)

    if expires_at is not None:
        item.expires_at = expires_at

    session.flush()
    return item
