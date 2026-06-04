from app.models import PantryItem
from app.normalize import normalize_ingredient_name, normalize_unit


def ingredient_key(ingredient_name: str, unit: str) -> tuple[str, str] | None:
    """Canonical (ingredient_name, unit) for same-unit pantry/recipe matching."""
    try:
        return normalize_ingredient_name(ingredient_name), normalize_unit(unit)
    except ValueError:
        return None


def build_pantry_map(items: list[PantryItem]) -> dict[tuple[str, str], float]:
    pantry_map: dict[tuple[str, str], float] = {}
    for item in items:
        key = ingredient_key(item.ingredient_name, item.unit)
        if key is None:
            continue
        pantry_map[key] = pantry_map.get(key, 0.0) + item.quantity
    return pantry_map
