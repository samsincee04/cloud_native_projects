from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cookability import list_cook_now, list_cookable_recipes
from app.shopping_list import (
    get_shopping_list_for_plan,
    patch_shopping_list_item_checked,
    regenerate_shopping_list,
)
from app.db import create_tables, get_session
from app.meal_plans import (
    create_meal_plan,
    delete_meal_plan,
    find_meal_plan,
    generate_meal_plan,
    get_meal_plan_or_404,
    meal_plan_response,
    replace_meal_plan_items,
)
from app.models import PantryEvent, PantryItem, Reminder, User
from app.pantry import (
    find_pantry_item,
    get_pantry_item_or_404,
    normalize_pantry_fields,
    pantry_event_response,
    pantry_item_response,
    record_event,
    require_user,
    upsert_pantry_item,
)
from app.schemas import (
    CookableRecipeItem,
    CookNowResponse,
    MealPlanCreateOrUpdateRequest,
    MealPlanGenerateRequest,
    MealPlanResponse,
    MissingSubstitutesRequest,
    MissingSubstitutesResponse,
    OkResponse,
    PantryEventApplyResponse,
    PantryEventCreateRequest,
    PantryEventsResponse,
    PantryItemCreateRequest,
    PantryItemResponse,
    PantryItemsResponse,
    PantryItemUpdateRequest,
    RecipeCreateRequest,
    RecipeDetailResponse,
    RecipeResponse,
    RecipeNutritionResponse,
    RecipeScaleResponse,
    SeedRecipesResponse,
    ShoppingListItemOut,
    ShoppingListItemPatchRequest,
    ShoppingListResponse,
    SubstituteEntry,
    SubstitutesResponse,
    NotificationResponse,
    NotificationsListResponse,
    NotificationsReadAllResponse,
    ReminderResponse,
    UserIdResponse,
)
from app.nutrition import get_recipe_nutrition
from app.recipes import (
    create_recipe,
    delete_recipe,
    get_recipe_detail,
    list_recipes,
    scale_recipe,
)
from app.normalize import normalize_ingredient_name
from app.seed_recipes import seed_recipes_from_file
from app.substitutions import get_substitutes, get_substitutes_for_many
from app.notifications import (
    list_notifications_for_user,
    mark_all_notifications_read,
    mark_notification_read,
)
from app.reminders import list_reminders_for_user

SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/admin/seed_recipes", response_model=SeedRecipesResponse)
def admin_seed_recipes(session: SessionDep):
    try:
        result = seed_recipes_from_file(session)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SeedRecipesResponse(**result)


@app.post("/users", response_model=UserIdResponse)
def create_user(session: SessionDep):
    user = User()
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserIdResponse(id=user.id)


@app.get("/recipes", response_model=list[RecipeResponse])
def list_recipes_endpoint(session: SessionDep):
    return list_recipes(session)


@app.post("/recipes", response_model=RecipeDetailResponse, status_code=201)
def create_recipe_endpoint(body: RecipeCreateRequest, session: SessionDep):
    return create_recipe(session, body)


@app.get("/recipes/{recipe_id}", response_model=RecipeDetailResponse)
def get_recipe_endpoint(recipe_id: UUID, session: SessionDep):
    return get_recipe_detail(session, recipe_id)


@app.get("/recipes/{recipe_id}/scale", response_model=RecipeScaleResponse)
def scale_recipe_endpoint(
    recipe_id: UUID,
    session: SessionDep,
    servings: float = Query(..., gt=0),
):
    return scale_recipe(session, recipe_id, servings)


@app.get("/recipes/{recipe_id}/nutrition", response_model=RecipeNutritionResponse)
def recipe_nutrition_endpoint(
    recipe_id: UUID,
    session: SessionDep,
    servings: float = Query(..., gt=0),
):
    calories, notes = get_recipe_nutrition(session, recipe_id, servings)
    return RecipeNutritionResponse(
        calories_per_serving=calories,
        notes=notes,
    )


@app.delete("/recipes/{recipe_id}", status_code=204)
def delete_recipe_endpoint(recipe_id: UUID, session: SessionDep):
    delete_recipe(session, recipe_id)


@app.get("/substitutions", response_model=SubstitutesResponse)
def substitutions_for_ingredient(
    ingredient_name: str = Query(..., min_length=1),
):
    subs = get_substitutes(ingredient_name)
    return SubstitutesResponse(
        ingredient_name=normalize_ingredient_name(ingredient_name),
        substitutes=[SubstituteEntry(**s) for s in subs],
    )


@app.post("/substitutions/missing", response_model=MissingSubstitutesResponse)
def substitutions_for_missing(body: MissingSubstitutesRequest):
    if not body.missing:
        return MissingSubstitutesResponse(substitutes={})
    raw = get_substitutes_for_many(body.missing)
    return MissingSubstitutesResponse(
        substitutes={
            ingredient: [SubstituteEntry(**s) for s in subs]
            for ingredient, subs in raw.items()
        }
    )


@app.get("/notifications", response_model=NotificationsListResponse)
def list_notifications(
    user_id: UUID,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
):
    items = list_notifications_for_user(session, user_id, limit=limit)
    return NotificationsListResponse(user_id=user_id, items=items)


@app.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read_endpoint(
    notification_id: UUID, session: SessionDep
):
    result = mark_notification_read(session, notification_id)
    session.commit()
    return result


@app.post("/notifications/read_all", response_model=NotificationsReadAllResponse)
def mark_all_notifications_read_endpoint(user_id: UUID, session: SessionDep):
    updated_count = mark_all_notifications_read(session, user_id)
    session.commit()
    return NotificationsReadAllResponse(
        user_id=user_id, updated_count=updated_count
    )


@app.get("/reminders", response_model=list[ReminderResponse])
def list_reminders(user_id: UUID, session: SessionDep):
    return list_reminders_for_user(session, user_id)


@app.post("/reminders/{id}/read", response_model=list[ReminderResponse])
def mark_reminder_read(id: UUID, session: SessionDep):
    reminder = session.get(Reminder, id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if not reminder.is_read:
        reminder.is_read = True
        session.commit()

    return list_reminders_for_user(session, reminder.user_id)


@app.post(
    "/meal_plans/{meal_plan_id}/shopping_list/generate",
    response_model=ShoppingListResponse,
)
def generate_meal_plan_shopping_list(meal_plan_id: UUID, session: SessionDep):
    result = regenerate_shopping_list(session, meal_plan_id)
    session.commit()
    return result


@app.get(
    "/meal_plans/{meal_plan_id}/shopping_list",
    response_model=ShoppingListResponse,
)
def get_meal_plan_shopping_list(meal_plan_id: UUID, session: SessionDep):
    return get_shopping_list_for_plan(session, meal_plan_id)


@app.patch(
    "/shopping_list_items/{item_id}",
    response_model=ShoppingListItemOut,
)
def patch_shopping_list_item(
    item_id: UUID,
    body: ShoppingListItemPatchRequest,
    session: SessionDep,
):
    result = patch_shopping_list_item_checked(session, item_id, body.checked)
    session.commit()
    return result


@app.get("/cookable_recipes", response_model=list[CookableRecipeItem])
def cookable_recipes(
    user_id: UUID,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
):
    require_user(session, user_id)
    return list_cookable_recipes(session, user_id, limit)


@app.get("/cook_now", response_model=CookNowResponse)
def cook_now(
    user_id: UUID,
    session: SessionDep,
    max_missing: int = Query(default=3, ge=0, le=50),
):
    require_user(session, user_id)
    return list_cook_now(session, user_id, max_missing)


@app.get("/pantry/items", response_model=PantryItemsResponse)
def list_pantry_items(user_id: UUID, session: SessionDep):
    require_user(session, user_id)
    items = session.scalars(
        select(PantryItem)
        .where(PantryItem.user_id == user_id)
        .order_by(PantryItem.ingredient_name)
    ).all()
    return PantryItemsResponse(
        user_id=user_id,
        items=[pantry_item_response(i) for i in items],
    )


@app.get("/pantry", response_model=list[PantryItemResponse])
def list_pantry_legacy(user_id: UUID, session: SessionDep):
    """Legacy alias for GET /pantry/items."""
    response = list_pantry_items(user_id, session)
    return response.items


@app.post("/pantry/items", response_model=PantryItemResponse)
def create_pantry_item(body: PantryItemCreateRequest, session: SessionDep):
    require_user(session, body.user_id)
    ingredient_name, unit = normalize_pantry_fields(
        body.ingredient_name, body.unit
    )

    if body.quantity <= 0:
        raise HTTPException(status_code=422, detail="quantity must be positive")

    record_event(
        session,
        user_id=body.user_id,
        ingredient_name=ingredient_name,
        delta=body.quantity,
        unit=unit,
        reason="added",
    )
    item = upsert_pantry_item(
        session,
        user_id=body.user_id,
        ingredient_name=ingredient_name,
        unit=unit,
        quantity_delta=body.quantity,
        expires_at=body.expires_at,
    )
    session.commit()
    session.refresh(item)
    return pantry_item_response(item)


@app.put("/pantry/items/{item_id}", response_model=PantryItemResponse)
def update_pantry_item(
    item_id: UUID, body: PantryItemUpdateRequest, session: SessionDep
):
    item = get_pantry_item_or_404(session, item_id)
    old_qty = item.quantity
    old_unit = item.unit
    ingredient_name = item.ingredient_name

    new_unit = old_unit
    if body.unit is not None:
        _, new_unit = normalize_pantry_fields(ingredient_name, body.unit)
        if new_unit != old_unit:
            conflict = find_pantry_item(
                session, item.user_id, ingredient_name, new_unit
            )
            if conflict is not None and conflict.id != item.id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Pantry item already exists for "
                        f"{ingredient_name} ({new_unit})"
                    ),
                )
            item.unit = new_unit

    if body.quantity is not None:
        if body.quantity < 0:
            raise HTTPException(
                status_code=422, detail="quantity must be >= 0"
            )
        item.quantity = body.quantity

    if body.expires_at is not None:
        item.expires_at = body.expires_at

    delta = item.quantity - old_qty
    reason = "adjusted" if delta != 0 else "edited"
    record_event(
        session,
        user_id=item.user_id,
        ingredient_name=ingredient_name,
        delta=delta,
        unit=item.unit,
        reason=reason,
    )
    session.commit()
    session.refresh(item)
    return pantry_item_response(item)


@app.delete("/pantry/items/{item_id}", response_model=OkResponse)
def delete_pantry_item(item_id: UUID, session: SessionDep):
    item = get_pantry_item_or_404(session, item_id)
    record_event(
        session,
        user_id=item.user_id,
        ingredient_name=item.ingredient_name,
        delta=-item.quantity,
        unit=item.unit,
        reason="removed",
    )
    session.delete(item)
    session.commit()
    return OkResponse()


@app.get("/pantry/events", response_model=PantryEventsResponse)
def list_pantry_events(
    user_id: UUID,
    session: SessionDep,
    limit: int = Query(default=200, ge=1, le=1000),
):
    require_user(session, user_id)
    events = session.scalars(
        select(PantryEvent)
        .where(PantryEvent.user_id == user_id)
        .order_by(PantryEvent.created_at.desc())
        .limit(limit)
    ).all()
    return PantryEventsResponse(
        user_id=user_id,
        items=[pantry_event_response(e) for e in events],
    )


@app.post("/pantry/events", response_model=PantryEventApplyResponse)
def create_pantry_event(body: PantryEventCreateRequest, session: SessionDep):
    require_user(session, body.user_id)
    ingredient_name, unit = normalize_pantry_fields(
        body.ingredient_name, body.unit
    )

    event = record_event(
        session,
        user_id=body.user_id,
        ingredient_name=ingredient_name,
        delta=body.delta,
        unit=unit,
        reason=body.reason,
    )
    item = upsert_pantry_item(
        session,
        user_id=body.user_id,
        ingredient_name=ingredient_name,
        unit=unit,
        quantity_delta=body.delta,
        expires_at=body.expires_at,
    )
    session.commit()
    session.refresh(item)
    session.refresh(event)
    return PantryEventApplyResponse(
        item=pantry_item_response(item),
        event=pantry_event_response(event),
    )


@app.get("/meal_plans/current", response_model=MealPlanResponse)
def get_current_meal_plan(
    user_id: UUID,
    week_start_date: date,
    session: SessionDep,
):
    require_user(session, user_id)
    plan = find_meal_plan(session, user_id, week_start_date)
    if plan is None:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return meal_plan_response(plan)


@app.post("/meal_plans/generate", response_model=MealPlanResponse)
def post_generate_meal_plan(
    user_id: UUID,
    body: MealPlanGenerateRequest,
    session: SessionDep,
):
    """
    Auto-fill Mon–Sun for one meal_type using pantry-aware recipe scoring.

    Overwrites items if a plan already exists for that week (same plan id).
    """
    plan = generate_meal_plan(session, user_id, body)
    session.commit()
    plan = get_meal_plan_or_404(session, plan.id)
    return meal_plan_response(plan)


@app.post("/meal_plans", response_model=MealPlanResponse, status_code=201)
def post_meal_plan(
    user_id: UUID,
    body: MealPlanCreateOrUpdateRequest,
    session: SessionDep,
):
    plan = create_meal_plan(
        session, user_id, body.week_start_date, body.items
    )
    session.commit()
    plan = get_meal_plan_or_404(session, plan.id)
    return meal_plan_response(plan)


@app.put("/meal_plans/{meal_plan_id}", response_model=MealPlanResponse)
def put_meal_plan(
    meal_plan_id: UUID,
    body: MealPlanCreateOrUpdateRequest,
    session: SessionDep,
):
    plan = replace_meal_plan_items(
        session, meal_plan_id, body.week_start_date, body.items
    )
    session.commit()
    plan = get_meal_plan_or_404(session, plan.id)
    return meal_plan_response(plan)


@app.delete("/meal_plans/{meal_plan_id}", status_code=204)
def remove_meal_plan(meal_plan_id: UUID, session: SessionDep):
    delete_meal_plan(session, meal_plan_id)
    session.commit()
