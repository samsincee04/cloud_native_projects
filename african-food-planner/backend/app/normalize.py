import re

ALLOWED_UNITS = frozenset({"g", "kg", "ml", "l", "tsp", "tbsp", "cup", "piece"})

_UNIT_ALIASES: dict[str, str] = {
    "gram": "g",
    "grams": "g",
    "g": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "kg": "kg",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "ml": "ml",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "l": "l",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbsp": "tbsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tsp": "tsp",
    "cup": "cup",
    "cups": "cup",
    "piece": "piece",
    "pieces": "piece",
}


def normalize_ingredient_name(name: str) -> str:
    """Lowercase, trim, collapse whitespace, and lightly singularize each word."""
    collapsed = re.sub(r"\s+", " ", name.strip().lower())
    if not collapsed:
        return collapsed
    return " ".join(_singularize_token(word) for word in collapsed.split(" "))


def _singularize_token(word: str) -> str:
    """Light plural → singular rules for pantry ingredient tokens."""
    if len(word) <= 2:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes"):
        return word[:-2]
    if word.endswith("es") and len(word) > 3:
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def normalize_unit(unit: str) -> str:
    """Map common unit variants to canonical short forms and validate."""
    key = re.sub(r"\s+", " ", unit.strip().lower())
    if not key:
        raise ValueError("Unit cannot be empty")

    canonical = _UNIT_ALIASES.get(key)
    if canonical is None:
        raise ValueError(
            f"Unknown unit '{unit}'. Allowed: {', '.join(sorted(ALLOWED_UNITS))}"
        )
    return canonical
