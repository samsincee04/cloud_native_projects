"""
Rough per-ingredient calorie factors for MVP nutrition estimates (no external APIs).
Values are approximate kcal per gram, ml, or piece.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Recipe, RecipeIngredient
from app.normalize import normalize_ingredient_name
from app.units import to_base_quantity

# kcal per 1 gram (dry/raw weights unless noted)
KCAL_PER_GRAM: dict[str, float] = {
    "rice": 3.6,
    "jasmine rice": 3.6,
    "basmati rice": 3.5,
    "brown rice": 3.7,
    "garri": 3.5,
    "cassava": 1.6,
    "cassava flour": 3.5,
    "fufu flour": 3.4,
    "semolina": 3.6,
    "yam": 1.18,
    "sweet potato": 0.86,
    "potato": 0.77,
    "plantain": 1.22,
    "green banana": 1.0,
    "black eyed pea": 3.4,
    "brown bean": 3.4,
    "kidney bean": 3.3,
    "lentil": 3.5,
    "egusi": 5.7,
    "ground pumpkin seed": 5.6,
    "peanut": 5.7,
    "groundnut": 5.7,
    "ogbono": 5.5,
    "chicken": 1.65,
    "chicken breast": 1.2,
    "chicken thigh": 2.1,
    "beef": 2.5,
    "goat meat": 2.0,
    "lamb": 2.9,
    "fish": 1.2,
    "smoked fish": 1.5,
    "stockfish": 0.8,
    "dried fish": 1.0,
    "shrimp": 1.0,
    "crayfish": 2.5,
    "dried shrimp": 2.5,
    "tomato": 0.18,
    "fresh tomato": 0.18,
    "tomato paste": 0.8,
    "onion": 0.4,
    "garlic": 1.5,
    "ginger": 0.8,
    "bell pepper": 0.31,
    "carrot": 0.41,
    "spinach": 0.23,
    "bitter leaf": 0.25,
    "okra": 0.33,
    "flour": 3.6,
    "wheat flour": 3.6,
    "sugar": 4.0,
    "salt": 0.0,
    "maggi": 0.5,
    "seasoning cube": 0.5,
    "bread": 2.65,
    "millet": 3.8,
    "sorghum": 3.4,
    "cornmeal": 3.7,
    "butter": 7.2,
    "margarine": 7.2,
}

# kcal per 1 ml (oils, milks, liquids ~ water density unless noted)
KCAL_PER_ML: dict[str, float] = {
    "palm oil": 8.8,
    "vegetable oil": 8.8,
    "coconut oil": 8.6,
    "red palm oil": 8.8,
    "olive oil": 8.8,
    "coconut milk": 2.3,
    "milk": 0.64,
    "evaporated milk": 1.3,
    "water": 0.0,
    "stock": 0.15,
    "chicken stock": 0.15,
    "beef stock": 0.15,
    "tomato paste": 0.95,
    "fish sauce": 0.6,
}

# kcal per piece (typical medium sizes)
KCAL_PER_PIECE: dict[str, float] = {
    "egg": 78.0,
    "onion": 44.0,
    "scotch bonnet": 18.0,
    "habanero": 18.0,
    "lime": 20.0,
    "lemon": 17.0,
    "plantain": 180.0,
    "bay leaf": 0.0,
    "seasoning cube": 5.0,
    "maggi": 5.0,
}

NOTES_ESTIMATE = "rough estimate"
NOTES_INSUFFICIENT = (
    "insufficient recognized ingredients for a calorie estimate"
)

# Require at least this share of required (non-optional) ingredients to be known
MIN_RECOGNIZED_FRACTION = 0.5


def _lookup_kcal_per_base_unit(ingredient_name: str, base_unit: str) -> float | None:
    if base_unit == "g":
        return KCAL_PER_GRAM.get(ingredient_name)
    if base_unit == "ml":
        return KCAL_PER_ML.get(ingredient_name)
    if base_unit == "piece":
        return KCAL_PER_PIECE.get(ingredient_name)
    return None


def ingredient_calories(ingredient_name: str, quantity: float, unit: str) -> float | None:
    """Return kcal for one ingredient line, or None if unknown."""
    name = normalize_ingredient_name(ingredient_name)
    if not name:
        return None
    try:
        base_qty, base_unit = to_base_quantity(quantity, unit)
    except ValueError:
        return None
    rate = _lookup_kcal_per_base_unit(name, base_unit)
    if rate is None:
        return None
    return base_qty * rate


def estimate_recipe_calories(
    recipe: Recipe, servings_target: float
) -> tuple[float | None, str]:
    servings_base = float(recipe.servings_base)
    if servings_base <= 0:
        raise ValueError("Recipe servings_base must be positive")
    if servings_target <= 0:
        raise ValueError("servings must be positive")

    scale = servings_target / servings_base
    required: list[RecipeIngredient] = [
        ing for ing in recipe.ingredients if not ing.optional
    ]
    if not required:
        return None, NOTES_INSUFFICIENT

    recognized = 0
    total_kcal = 0.0
    for ing in required:
        qty = float(ing.quantity) * scale
        kcal = ingredient_calories(ing.ingredient_name, qty, ing.unit)
        if kcal is None:
            continue
        recognized += 1
        total_kcal += kcal

    if recognized / len(required) < MIN_RECOGNIZED_FRACTION:
        return None, NOTES_INSUFFICIENT

    per_serving = total_kcal / servings_target
    return round(per_serving, 1), NOTES_ESTIMATE


def get_recipe_nutrition(
    session: Session, recipe_id: UUID, servings: float
) -> tuple[float | None, str]:
    from fastapi import HTTPException

    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients))
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    try:
        return estimate_recipe_calories(recipe, servings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
