"""Unit normalization, conversion, and shopping-friendly display."""

from __future__ import annotations

import math

from app.normalize import normalize_ingredient_name, normalize_unit

# Re-export for callers that import from the unit system module.
__all__ = [
    "normalize_unit",
    "convert_qty",
    "to_base_quantity",
    "base_to_display_qty",
    "accumulate_base_quantity",
    "sum_pantry_in_base",
]

# 1 tbsp = 3 tsp, 1 cup = 16 tbsp; 1 cup = 240 ml => 5 ml/tsp, 15 ml/tbsp
ML_PER_TSP = 5.0
ML_PER_TBSP = 15.0
ML_PER_CUP = 240.0

_TO_GRAMS: dict[str, float] = {"g": 1.0, "kg": 1000.0}
_TO_ML: dict[str, float] = {
    "ml": 1.0,
    "l": 1000.0,
    "tsp": ML_PER_TSP,
    "tbsp": ML_PER_TBSP,
    "cup": ML_PER_CUP,
}

WEIGHT_UNITS = frozenset(_TO_GRAMS)
VOLUME_UNITS = frozenset(_TO_ML)
BASE_UNITS = frozenset({"g", "ml", "piece"})


def to_base_quantity(qty: float, unit: str) -> tuple[float, str]:
    """Convert qty to accumulator base: grams, milliliters, or pieces."""
    canonical = normalize_unit(unit)
    if canonical in _TO_GRAMS:
        return qty * _TO_GRAMS[canonical], "g"
    if canonical in _TO_ML:
        return qty * _TO_ML[canonical], "ml"
    if canonical == "piece":
        return qty, "piece"
    raise ValueError(f"Unknown unit '{unit}'")


def convert_qty(qty: float, from_unit: str, to_unit: str) -> float:
    """Convert between units in the same family (weight, volume, or piece)."""
    from_u = normalize_unit(from_unit)
    to_u = normalize_unit(to_unit)
    if from_u == to_u:
        return qty
    if from_u == "piece" or to_u == "piece":
        raise ValueError("Pieces cannot be converted")

    if from_u in _TO_GRAMS and to_u in _TO_GRAMS:
        grams = qty * _TO_GRAMS[from_u]
        return grams / _TO_GRAMS[to_u]
    if from_u in _TO_ML and to_u in _TO_ML:
        ml = qty * _TO_ML[from_u]
        return ml / _TO_ML[to_u]
    raise ValueError(f"Cannot convert {from_u} to {to_u}")


def choose_display_unit(base_qty: float, base_unit: str) -> str:
    if base_unit == "g":
        return "kg" if base_qty >= 1000 else "g"
    if base_unit == "ml":
        return "l" if base_qty >= 1000 else "ml"
    return "piece"


def round_shopping_qty(qty: float, unit: str) -> float:
    canonical = normalize_unit(unit)
    if qty <= 0:
        return 0.0 if canonical != "piece" else 0.0
    if canonical == "piece":
        return float(math.ceil(qty - 1e-9))
    if canonical in {"tsp", "tbsp", "cup"}:
        return round(qty + 1e-9, 1)
    if canonical in {"g", "ml"}:
        return float(round(qty / 5) * 5)
    if canonical in {"kg", "l"}:
        return round(qty + 1e-9, 1)
    return qty


def base_to_display_qty(base_qty: float, base_unit: str) -> tuple[float, str]:
    """Map base accumulator qty to a friendly unit and rounded display qty."""
    display_unit = choose_display_unit(base_qty, base_unit)
    if display_unit == base_unit:
        display_qty = base_qty
    else:
        display_qty = convert_qty(base_qty, base_unit, display_unit)
    return round_shopping_qty(display_qty, display_unit), display_unit


def accumulate_base_quantity(
    totals: dict[tuple[str, str], float],
    ingredient_name: str,
    qty: float,
    unit: str,
) -> None:
    """Add qty into totals keyed by (normalized ingredient name, base unit)."""
    name = normalize_ingredient_name(ingredient_name)
    if not name:
        return
    try:
        base_qty, base_unit = to_base_quantity(qty, unit)
    except ValueError:
        return
    key = (name, base_unit)
    totals[key] = totals.get(key, 0.0) + base_qty


def sum_pantry_in_base(
    pantry_items: list,
    ingredient_name: str,
    base_unit: str,
) -> float:
    """Sum pantry rows for an ingredient, converting into base_unit when possible."""
    target_name = normalize_ingredient_name(ingredient_name)
    total = 0.0
    for item in pantry_items:
        name = normalize_ingredient_name(item.ingredient_name)
        if not name or name != target_name:
            continue
        try:
            item_base_qty, item_base_unit = to_base_quantity(
                float(item.quantity), item.unit
            )
        except ValueError:
            continue
        if item_base_unit != base_unit:
            continue
        total += item_base_qty
    return total


def display_shopping_amounts(
    needed_base: float,
    pantry_base: float,
    base_unit: str,
) -> tuple[float, float, float, str]:
    """Return (needed, in_pantry, to_buy, unit) in one consistent display unit."""
    reference = max(needed_base, pantry_base)
    display_unit = choose_display_unit(reference, base_unit)
    if display_unit == base_unit:
        needed_raw = needed_base
        pantry_raw = pantry_base
    else:
        needed_raw = convert_qty(needed_base, base_unit, display_unit)
        pantry_raw = convert_qty(pantry_base, base_unit, display_unit)
    to_buy_raw = max(0.0, needed_raw - pantry_raw)
    return (
        round_shopping_qty(needed_raw, display_unit),
        round_shopping_qty(pantry_raw, display_unit),
        round_shopping_qty(to_buy_raw, display_unit),
        display_unit,
    )
