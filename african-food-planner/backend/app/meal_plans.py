from collections import defaultdict
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.cookability import build_pantry_present_names, required_ingredient_names
from app.models import MealPlan, MealPlanItem, PantryItem, Recipe
from app.pantry import require_user
from app.schemas import (
    MealPlanGenerateRequest,
    MealPlanItemIn,
    MealPlanItemOut,
    MealPlanResponse,
)

ALLOWED_MEAL_TYPES = frozenset({"breakfast", "lunch", "dinner"})


def validate_meal_slot(day: int, meal_type: str) -> str:
    if day < 0 or day > 6:
        raise HTTPException(status_code=422, detail="day must be between 0 and 6")
    normalized = meal_type.strip().lower()
    if normalized not in ALLOWED_MEAL_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"meal_type must be one of: {', '.join(sorted(ALLOWED_MEAL_TYPES))}",
        )
    return normalized


def require_recipe(session: Session, recipe_id: UUID) -> Recipe:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


def get_meal_plan_or_404(session: Session, plan_id: UUID) -> MealPlan:
    plan = session.scalar(
        select(MealPlan)
        .where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.items))
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return plan


def find_meal_plan(
    session: Session, user_id: UUID, week_start_date: date
) -> MealPlan | None:
    return session.scalar(
        select(MealPlan)
        .where(
            MealPlan.user_id == user_id,
            MealPlan.week_start_date == week_start_date,
        )
        .options(selectinload(MealPlan.items))
    )


def meal_plan_item_out(item: MealPlanItem) -> MealPlanItemOut:
    return MealPlanItemOut(
        id=item.id,
        day=item.day_of_week,
        meal_type=item.meal_type,
        recipe_id=item.recipe_id,
        servings=item.servings,
    )


def meal_plan_response(plan: MealPlan) -> MealPlanResponse:
    items = sorted(
        plan.items,
        key=lambda i: (i.day_of_week, i.meal_type),
    )
    return MealPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        week_start_date=plan.week_start_date,
        items=[meal_plan_item_out(i) for i in items],
    )


def validate_items_for_insert(
    session: Session, items: list[MealPlanItemIn]
) -> list[tuple[int, str, UUID, float]]:
    seen: set[tuple[int, str]] = set()
    normalized: list[tuple[int, str, UUID, float]] = []
    for item in items:
        meal_type = validate_meal_slot(item.day, item.meal_type)
        key = (item.day, meal_type)
        if key in seen:
            raise HTTPException(
                status_code=422,
                detail="duplicate day and meal_type in items",
            )
        seen.add(key)
        require_recipe(session, item.recipe_id)
        if item.servings <= 0:
            raise HTTPException(status_code=422, detail="servings must be positive")
        normalized.append((item.day, meal_type, item.recipe_id, item.servings))
    return normalized


def insert_meal_plan_items(
    session: Session,
    plan_id: UUID,
    rows: list[tuple[int, str, UUID, float]],
) -> None:
    for day, meal_type, recipe_id, servings in rows:
        session.add(
            MealPlanItem(
                meal_plan_id=plan_id,
                day_of_week=day,
                meal_type=meal_type,
                recipe_id=recipe_id,
                servings=servings,
            )
        )


def create_meal_plan(
    session: Session,
    user_id: UUID,
    week_start_date: date,
    items: list[MealPlanItemIn],
) -> MealPlan:
    require_user(session, user_id)
    if find_meal_plan(session, user_id, week_start_date) is not None:
        raise HTTPException(
            status_code=409,
            detail="Meal plan already exists for this week",
        )
    plan = MealPlan(user_id=user_id, week_start_date=week_start_date)
    session.add(plan)
    session.flush()
    rows = validate_items_for_insert(session, items)
    insert_meal_plan_items(session, plan.id, rows)
    return plan


def replace_meal_plan_items(
    session: Session,
    plan_id: UUID,
    week_start_date: date,
    items: list[MealPlanItemIn],
) -> MealPlan:
    plan = get_meal_plan_or_404(session, plan_id)
    if plan.week_start_date != week_start_date:
        raise HTTPException(
            status_code=422,
            detail="week_start_date does not match this meal plan",
        )
    rows = validate_items_for_insert(session, items)
    for existing in list(plan.items):
        session.delete(existing)
    session.flush()
    insert_meal_plan_items(session, plan.id, rows)
    return plan


def delete_meal_plan(session: Session, plan_id: UUID) -> None:
    plan = get_meal_plan_or_404(session, plan_id)
    session.delete(plan)


def _normalize_tag_set(tags: list[str]) -> set[str]:
    return {tag.strip().lower() for tag in tags if tag.strip()}


def _recipe_matches_tags(
    recipe: Recipe, include_tags: set[str], exclude_tags: set[str]
) -> bool:
    recipe_tags = _normalize_tag_set(list(recipe.tags_json or []))
    if exclude_tags and recipe_tags.intersection(exclude_tags):
        return False
    if include_tags and not include_tags.issubset(recipe_tags):
        return False
    return True


def _score_recipe(recipe: Recipe, pantry_present: set[str]) -> tuple[int, int, int]:
    """Return (score, missing_count, ingredient_count). Lower score is better."""
    required_names, ingredient_count = required_ingredient_names(recipe)
    missing_count = sum(1 for name in required_names if name not in pantry_present)
    score = (missing_count * 10) - ingredient_count
    return score, missing_count, ingredient_count


def _pick_week_recipes(
    candidates: list[tuple[Recipe, int, int]],
    max_repeats_per_week: int,
    max_missing_ingredients: int,
) -> list[Recipe]:
    if not candidates:
        raise HTTPException(
            status_code=422,
            detail="No recipes match the filters",
        )

    max_missing_cap = max(missing for _, _score, missing in candidates)

    for threshold in range(max_missing_ingredients, max_missing_cap + 1):
        repeat_count: dict[UUID, int] = defaultdict(int)
        picked: list[Recipe] = []
        for _day in range(7):
            chosen: Recipe | None = None
            for recipe, _score, missing_count in candidates:
                if missing_count > threshold:
                    continue
                if repeat_count[recipe.id] >= max_repeats_per_week:
                    continue
                chosen = recipe
                break
            if chosen is None:
                picked = []
                break
            repeat_count[chosen.id] += 1
            picked.append(chosen)
        if len(picked) == 7:
            return picked

    raise HTTPException(
        status_code=422,
        detail="Could not build a 7-day plan with available recipes and constraints",
    )


def generate_meal_plan(
    session: Session, user_id: UUID, body: MealPlanGenerateRequest
) -> MealPlan:
    """
    Heuristic weekly plan from pantry coverage and recipe tags.

    If a plan already exists for (user_id, week_start_date), its items are
    replaced (overwrite). The plan id and shopping list row are kept.
    """
    require_user(session, user_id)
    meal_type = validate_meal_slot(0, body.meal_type)

    include_tags = _normalize_tag_set(body.include_tags)
    exclude_tags = _normalize_tag_set(body.exclude_tags)

    pantry_items = session.scalars(
        select(PantryItem).where(PantryItem.user_id == user_id)
    ).all()
    pantry_present = build_pantry_present_names(list(pantry_items))

    recipes = session.scalars(
        select(Recipe).options(selectinload(Recipe.ingredients))
    ).all()

    filtered: list[Recipe] = []
    for recipe in recipes:
        if not _recipe_matches_tags(recipe, include_tags, exclude_tags):
            continue
        required_names, _ = required_ingredient_names(recipe)
        if not required_names:
            continue
        filtered.append(recipe)

    candidates: list[tuple[Recipe, int, int]] = []
    for recipe in filtered:
        score, missing_count, _ingredient_count = _score_recipe(recipe, pantry_present)
        candidates.append((recipe, score, missing_count))
    candidates.sort(key=lambda row: row[1])

    week_recipes = _pick_week_recipes(
        candidates,
        body.max_repeats_per_week,
        body.max_missing_ingredients,
    )

    rows: list[tuple[int, str, UUID, float]] = [
        (day, meal_type, recipe.id, body.servings)
        for day, recipe in enumerate(week_recipes)
    ]

    existing = find_meal_plan(session, user_id, body.week_start_date)
    if existing is None:
        plan = MealPlan(user_id=user_id, week_start_date=body.week_start_date)
        session.add(plan)
        session.flush()
        insert_meal_plan_items(session, plan.id, rows)
        return plan

    for item in list(existing.items):
        session.delete(item)
    session.flush()
    insert_meal_plan_items(session, existing.id, rows)
    return existing
