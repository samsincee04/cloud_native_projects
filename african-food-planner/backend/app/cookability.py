from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ingredients import build_pantry_map, ingredient_key
from app.models import PantryItem, Recipe
from app.normalize import normalize_ingredient_name
from app.schemas import (
    CookableMissingIngredient,
    CookableRecipeItem,
    CookNowRecipeItem,
    CookNowResponse,
)
from app.substitutions import substitution_names_for_missing


def score_recipe(
    recipe: Recipe, pantry_map: dict[tuple[str, str], float]
) -> tuple[CookableRecipeItem, int]:
    missing: list[CookableMissingIngredient] = []
    covered_count = 0

    # MVP: all recipe ingredients are required (ignore optional flag).
    for ing in recipe.ingredients:
        key = ingredient_key(ing.ingredient_name, ing.unit)
        needed_qty = float(ing.quantity)

        if key is None:
            missing.append(
                CookableMissingIngredient(
                    ingredient_name=normalize_ingredient_name(ing.ingredient_name),
                    needed_qty=needed_qty,
                    unit=ing.unit.strip().lower(),
                    pantry_qty=0.0,
                )
            )
            continue

        ingredient_name, unit = key
        pantry_qty = pantry_map.get(key, 0.0)

        if pantry_qty >= needed_qty:
            covered_count += 1
        else:
            missing.append(
                CookableMissingIngredient(
                    ingredient_name=ingredient_name,
                    needed_qty=needed_qty,
                    unit=unit,
                    pantry_qty=pantry_qty,
                )
            )

    missing_count = len(missing)
    item = CookableRecipeItem(
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        servings_base=float(recipe.servings_base),
        cookable=missing_count == 0,
        missing_count=missing_count,
        missing=missing,
    )
    return item, covered_count


def list_cookable_recipes(
    session: Session, user_id: UUID, limit: int
) -> list[CookableRecipeItem]:
    pantry_items = session.scalars(
        select(PantryItem).where(PantryItem.user_id == user_id)
    ).all()
    pantry_map = build_pantry_map(list(pantry_items))

    recipes = session.scalars(
        select(Recipe).options(selectinload(Recipe.ingredients))
    ).all()

    scored: list[tuple[CookableRecipeItem, int]] = [
        score_recipe(recipe, pantry_map) for recipe in recipes
    ]
    scored.sort(key=lambda pair: (not pair[0].cookable, pair[0].missing_count, -pair[1]))
    return [item for item, _ in scored[:limit]]


def build_pantry_present_names(items: list[PantryItem]) -> set[str]:
    """Ingredient names with any pantry row where quantity > 0 (unit ignored)."""
    present: set[str] = set()
    for item in items:
        if item.quantity <= 0:
            continue
        name = normalize_ingredient_name(item.ingredient_name)
        if name:
            present.add(name)
    return present


def required_ingredient_names(recipe: Recipe) -> tuple[list[str], int]:
    """Unique normalized required names and total non-optional ingredient rows."""
    names: list[str] = []
    seen: set[str] = set()
    total = 0
    for ing in recipe.ingredients:
        if ing.optional:
            continue
        total += 1
        name = normalize_ingredient_name(ing.ingredient_name)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names, total


def list_cook_now(
    session: Session, user_id: UUID, max_missing: int
) -> CookNowResponse:
    pantry_items = session.scalars(
        select(PantryItem).where(PantryItem.user_id == user_id)
    ).all()
    pantry_present = build_pantry_present_names(list(pantry_items))

    recipes = session.scalars(
        select(Recipe).options(selectinload(Recipe.ingredients))
    ).all()

    can_cook: list[tuple[CookNowRecipeItem, int]] = []
    almost: list[tuple[CookNowRecipeItem, int]] = []

    for recipe in recipes:
        required_names, ingredient_count = required_ingredient_names(recipe)
        missing = [name for name in required_names if name not in pantry_present]
        missing_count = len(missing)
        if missing_count == 0:
            item = CookNowRecipeItem(
                recipe_id=recipe.id,
                name=recipe.name,
                missing=missing,
            )
            can_cook.append((item, ingredient_count))
        elif missing_count <= max_missing:
            item = CookNowRecipeItem(
                recipe_id=recipe.id,
                name=recipe.name,
                missing=missing,
                substitutions=substitution_names_for_missing(missing),
            )
            almost.append((item, missing_count))

    can_cook.sort(key=lambda pair: -pair[1])
    almost.sort(key=lambda pair: pair[1])

    return CookNowResponse(
        can_cook=[item for item, _ in can_cook],
        almost=[item for item, _ in almost],
    )
