from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Recipe, RecipeIngredient
from app.normalize import normalize_ingredient_name, normalize_unit
from app.schemas import (
    RecipeCreateRequest,
    RecipeDetailResponse,
    RecipeIngredientResponse,
    RecipeScaleItem,
    RecipeScaleResponse,
    RecipeResponse,
)


def recipe_response(recipe: Recipe) -> RecipeResponse:
    return RecipeResponse(
        id=recipe.id,
        name=recipe.name,
        servings_base=float(recipe.servings_base),
        tags=recipe.tags_json or [],
        created_at=recipe.created_at,
    )


def recipe_detail_response(recipe: Recipe) -> RecipeDetailResponse:
    ingredients = sorted(recipe.ingredients, key=lambda i: i.ingredient_name)
    return RecipeDetailResponse(
        recipe=recipe_response(recipe),
        ingredients=[
            RecipeIngredientResponse.model_validate(i) for i in ingredients
        ],
        steps=recipe.steps_json,
    )


def normalize_recipe_ingredient(ingredient_name: str, unit: str) -> tuple[str, str]:
    try:
        return normalize_ingredient_name(ingredient_name), normalize_unit(unit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def list_recipes(session: Session) -> list[RecipeResponse]:
    recipes = session.scalars(
        select(Recipe).order_by(Recipe.created_at.desc())
    ).all()
    return [recipe_response(r) for r in recipes]


def get_recipe_detail(session: Session, recipe_id: UUID) -> RecipeDetailResponse:
    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients))
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe_detail_response(recipe)


def create_recipe(session: Session, body: RecipeCreateRequest) -> RecipeDetailResponse:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if body.servings_base <= 0:
        raise HTTPException(status_code=400, detail="servings_base must be positive")
    if not body.ingredients:
        raise HTTPException(status_code=400, detail="ingredients are required")

    recipe = Recipe(
        name=name,
        servings_base=float(body.servings_base),
        tags_json=body.tags,
        steps_json=body.steps,
    )
    session.add(recipe)

    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=400, detail="A recipe with this name already exists"
        ) from exc

    for ing in body.ingredients:
        if ing.quantity <= 0:
            raise HTTPException(
                status_code=400, detail="ingredient quantity must be positive"
            )
        ingredient_name, unit = normalize_recipe_ingredient(
            ing.ingredient_name, ing.unit
        )
        session.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_name=ingredient_name,
                quantity=float(ing.quantity),
                unit=unit,
                optional=ing.optional,
                category=ing.category,
            )
        )

    session.commit()
    session.refresh(recipe)
    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe.id)
        .options(selectinload(Recipe.ingredients))
    )
    assert recipe is not None
    return recipe_detail_response(recipe)


def delete_recipe(session: Session, recipe_id: UUID) -> None:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    try:
        session.delete(recipe)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail="Cannot delete recipe: it is referenced by a meal plan",
        ) from exc


def _display_round(qty: float) -> float:
    nearest_int = round(qty)
    if abs(qty - nearest_int) < 0.01:
        return float(nearest_int)
    return round(qty, 2)


def scale_recipe(
    session: Session, recipe_id: UUID, servings_target: float
) -> RecipeScaleResponse:
    if servings_target <= 0:
        raise HTTPException(status_code=400, detail="servings must be positive")

    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients))
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    servings_base = float(recipe.servings_base)
    if servings_base <= 0:
        raise HTTPException(status_code=400, detail="Recipe servings_base must be positive")

    factor = float(servings_target) / servings_base
    items = [
        RecipeScaleItem(
            ingredient_name=normalize_ingredient_name(ing.ingredient_name),
            unit=ing.unit,
            qty_base=_display_round(float(ing.quantity)),
            qty_scaled=_display_round(float(ing.quantity) * factor),
            optional=bool(ing.optional),
            category=ing.category,
        )
        for ing in sorted(recipe.ingredients, key=lambda i: i.ingredient_name)
    ]

    return RecipeScaleResponse(
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        servings_base=_display_round(servings_base),
        servings_target=_display_round(float(servings_target)),
        items=items,
    )
