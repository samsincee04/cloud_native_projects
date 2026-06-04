import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.normalize import normalize_ingredient_name, normalize_unit
from app.models import Recipe, RecipeIngredient

REPO_ROOT = Path(__file__).resolve().parents[2]


def recipes_seed_path() -> Path:
    if env_path := os.environ.get("RECIPES_SEED_PATH"):
        return Path(env_path)
    return REPO_ROOT / "data" / "recipes_seed.json"


def load_seed_data(path: Path | None = None) -> list[dict]:
    seed_path = path or recipes_seed_path()
    if not seed_path.is_file():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    try:
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in seed file: {exc}") from exc
    recipes = payload.get("recipes", payload)
    if not isinstance(recipes, list):
        raise ValueError("Seed file must contain a 'recipes' array")
    return recipes


def seed_recipes_from_file(session: Session, path: Path | None = None) -> dict:
    entries = load_seed_data(path)
    created = 0
    updated = 0

    for entry in entries:
        recipe = session.scalar(select(Recipe).where(Recipe.name == entry["name"]))
        is_new = recipe is None

        if is_new:
            recipe = Recipe(
                name=entry["name"],
                servings_base=float(entry["servings_base"]),
                tags_json=entry.get("tags", []),
                steps_json=entry.get("steps"),
            )
            session.add(recipe)
            session.flush()
            created += 1
        else:
            recipe.servings_base = float(entry["servings_base"])
            recipe.tags_json = entry.get("tags", [])
            recipe.steps_json = entry.get("steps")
            updated += 1

        for ingredient in list(recipe.ingredients):
            session.delete(ingredient)
        session.flush()

        for ing in entry["ingredients"]:
            try:
                ingredient_name = normalize_ingredient_name(ing["name"])
                unit = normalize_unit(ing["unit"])
            except ValueError:
                ingredient_name = normalize_ingredient_name(ing["name"])
                unit = ing["unit"].strip().lower()
            session.add(
                RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_name=ingredient_name,
                    quantity=float(ing["qty"]),
                    unit=unit,
                    optional=bool(ing.get("optional", False)),
                    category=ing.get("category"),
                )
            )

    session.commit()
    return {
        "created": created,
        "updated": updated,
        "total": len(entries),
        "seed_file": str(path or recipes_seed_path()),
    }
