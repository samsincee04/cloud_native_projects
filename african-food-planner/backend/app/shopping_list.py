from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.meal_plans import get_meal_plan_or_404
from app.models import MealPlan, PantryItem, Recipe, ShoppingList, ShoppingListItem
from app.schemas import ShoppingListItemOut, ShoppingListResponse
from app.units import (
    accumulate_base_quantity,
    display_shopping_amounts,
    sum_pantry_in_base,
)


def compute_needed_quantities(
    session: Session, plan: MealPlan
) -> dict[tuple[str, str], float]:
    """Needed totals keyed by (ingredient_name, base unit) in g, ml, or piece."""
    needed: dict[tuple[str, str], float] = {}
    if not plan.items:
        return needed

    recipe_ids = {item.recipe_id for item in plan.items}
    recipes = session.scalars(
        select(Recipe)
        .where(Recipe.id.in_(recipe_ids))
        .options(selectinload(Recipe.ingredients))
    ).all()
    recipe_by_id = {recipe.id: recipe for recipe in recipes}

    for meal_item in plan.items:
        recipe = recipe_by_id.get(meal_item.recipe_id)
        if recipe is None or recipe.servings_base <= 0:
            continue
        scale = float(meal_item.servings) / float(recipe.servings_base)
        for ing in recipe.ingredients:
            accumulate_base_quantity(
                needed,
                ing.ingredient_name,
                float(ing.quantity) * scale,
                ing.unit,
            )

    return needed


def shopping_list_response(shopping_list: ShoppingList) -> ShoppingListResponse:
    items = sorted(
        shopping_list.items,
        key=lambda row: (row.ingredient_name, row.unit),
    )
    return ShoppingListResponse(
        id=shopping_list.id,
        meal_plan_id=shopping_list.meal_plan_id,
        items=[
            ShoppingListItemOut(
                id=item.id,
                ingredient_name=item.ingredient_name,
                unit=item.unit,
                needed_qty=item.needed_qty,
                in_pantry_qty=item.in_pantry_qty,
                to_buy_qty=item.to_buy_qty,
                checked=item.checked,
            )
            for item in items
        ],
    )


def get_shopping_list_for_plan(
    session: Session, meal_plan_id: UUID
) -> ShoppingListResponse:
    get_meal_plan_or_404(session, meal_plan_id)
    shopping_list = session.scalar(
        select(ShoppingList)
        .where(ShoppingList.meal_plan_id == meal_plan_id)
        .options(selectinload(ShoppingList.items))
    )
    if shopping_list is None:
        raise HTTPException(status_code=404, detail="Shopping list not found")
    return shopping_list_response(shopping_list)


def regenerate_shopping_list(
    session: Session, meal_plan_id: UUID
) -> ShoppingListResponse:
    plan = get_meal_plan_or_404(session, meal_plan_id)

    pantry_items = session.scalars(
        select(PantryItem).where(PantryItem.user_id == plan.user_id)
    ).all()
    needed = compute_needed_quantities(session, plan)

    shopping_list = session.scalar(
        select(ShoppingList)
        .where(ShoppingList.meal_plan_id == meal_plan_id)
        .options(selectinload(ShoppingList.items))
    )
    if shopping_list is None:
        shopping_list = ShoppingList(meal_plan_id=meal_plan_id)
        session.add(shopping_list)
        session.flush()
    else:
        for existing in list(shopping_list.items):
            session.delete(existing)
        session.flush()

    for (ingredient_name, base_unit), needed_base in sorted(
        needed.items(), key=lambda row: row[0][0]
    ):
        pantry_base = sum_pantry_in_base(
            list(pantry_items), ingredient_name, base_unit
        )
        needed_qty, in_pantry_qty, to_buy_qty, unit = display_shopping_amounts(
            needed_base, pantry_base, base_unit
        )
        session.add(
            ShoppingListItem(
                shopping_list_id=shopping_list.id,
                ingredient_name=ingredient_name,
                unit=unit,
                needed_qty=needed_qty,
                in_pantry_qty=in_pantry_qty,
                to_buy_qty=to_buy_qty,
                checked=False,
            )
        )

    session.flush()
    session.refresh(shopping_list)
    shopping_list = session.scalar(
        select(ShoppingList)
        .where(ShoppingList.id == shopping_list.id)
        .options(selectinload(ShoppingList.items))
    )
    assert shopping_list is not None
    return shopping_list_response(shopping_list)


def patch_shopping_list_item_checked(
    session: Session, item_id: UUID, checked: bool
) -> ShoppingListItemOut:
    item = session.get(ShoppingListItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Shopping list item not found")

    item.checked = checked
    session.flush()
    return ShoppingListItemOut(
        id=item.id,
        ingredient_name=item.ingredient_name,
        unit=item.unit,
        needed_qty=item.needed_qty,
        in_pantry_qty=item.in_pantry_qty,
        to_buy_qty=item.to_buy_qty,
        checked=item.checked,
    )
