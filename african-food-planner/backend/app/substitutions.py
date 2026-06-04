"""
Hardcoded ingredient substitution map for MVP (African staples & spices).
Keys are normalized via normalize_ingredient_name at load time.
"""

from app.normalize import normalize_ingredient_name

_RAW: dict[str, list[dict]] = {
    "palm oil": [
        {"substitute": "vegetable oil", "note": "Neutral; lacks palm colour and aroma.", "category": "oil"},
        {"substitute": "coconut oil", "note": "Rich mouthfeel; works in stews and rice.", "category": "oil"},
    ],
    "vegetable oil": [
        {"substitute": "palm oil", "note": "Adds West African character and colour.", "category": "oil"},
        {"substitute": "sunflower oil", "note": "Neutral high-heat oil.", "category": "oil"},
    ],
    "scotch bonnet": [
        {"substitute": "habanero", "note": "Closest heat and fruity flavour.", "category": "spice"},
        {"substitute": "bird eye chili", "note": "Smaller; use fewer pods for similar heat.", "category": "spice"},
    ],
    "habanero": [
        {"substitute": "scotch bonnet", "note": "Very similar in heat and flavour.", "category": "spice"},
        {"substitute": "jalapeño", "note": "Milder; add chili flakes to compensate.", "category": "spice"},
    ],
    "crayfish": [
        {"substitute": "shrimp powder", "note": "Closest umami; same quantity.", "category": "seasoning"},
        {"substitute": "fish sauce", "note": "Use ½ tsp per tbsp crayfish.", "category": "seasoning"},
    ],
    "dried shrimp": [
        {"substitute": "crayfish", "note": "Similar briny umami; grind if needed.", "category": "seasoning"},
        {"substitute": "shrimp powder", "note": "Fine grind; adjust salt.", "category": "seasoning"},
    ],
    "stockfish": [
        {"substitute": "smoked fish", "note": "Similar smoky savoury depth.", "category": "protein"},
        {"substitute": "dried catfish", "note": "Soak and flake before use.", "category": "protein"},
    ],
    "smoked fish": [
        {"substitute": "stockfish", "note": "Stronger umami; use less.", "category": "protein"},
        {"substitute": "smoked mackerel", "note": "Readily available fillets.", "category": "protein"},
    ],
    "dried fish": [
        {"substitute": "smoked fish", "note": "Comparable depth in soups.", "category": "protein"},
        {"substitute": "anchovy", "note": "Small amount for umami only.", "category": "protein"},
    ],
    "ogbono": [
        {"substitute": "okra", "note": "Similar draw/slime when cooked.", "category": "thickener"},
        {"substitute": "ground flax seed", "note": "Neutral binder; use sparingly.", "category": "thickener"},
    ],
    "okra": [
        {"substitute": "ogbono", "note": "Seed thickener instead of whole okra.", "category": "thickener"},
        {"substitute": "file powder", "note": "Adds body to gumbo-style dishes.", "category": "thickener"},
    ],
    "egusi": [
        {"substitute": "ground pumpkin seed", "note": "Closest nutty seed swap.", "category": "seed"},
        {"substitute": "sunflower seed", "note": "Grind fine; milder flavour.", "category": "seed"},
    ],
    "groundnut": [
        {"substitute": "peanut", "note": "Same legume; interchangeable.", "category": "seed"},
        {"substitute": "peanut butter", "note": "Smooth soups; reduce added oil.", "category": "seed"},
    ],
    "peanut": [
        {"substitute": "groundnut", "note": "Direct equivalent.", "category": "seed"},
        {"substitute": "cashew", "note": "Milder; works in sauces.", "category": "seed"},
    ],
    "plantain": [
        {"substitute": "sweet potato", "note": "Starchy side for savoury plates.", "category": "produce"},
        {"substitute": "green banana", "note": "Firmer; better for frying.", "category": "produce"},
    ],
    "gari": [
        {"substitute": "semolina", "note": "Good swallow texture.", "category": "grain"},
        {"substitute": "cassava flour", "note": "Same root; adjust water.", "category": "grain"},
    ],
    "fufu flour": [
        {"substitute": "pounded yam flour", "note": "Closest swallow texture.", "category": "grain"},
        {"substitute": "plantain flour", "note": "Slightly sweeter swallow.", "category": "grain"},
    ],
    "pounded yam": [
        {"substitute": "yam flour", "note": "Quick swallow substitute.", "category": "grain"},
        {"substitute": "cassava fufu", "note": "Stretchy alternative swallow.", "category": "grain"},
    ],
    "suya spice": [
        {"substitute": "peanut powder + paprika + ginger", "note": "Rub mix approximating suya profile.", "category": "spice blend"},
        {"substitute": "berbere", "note": "Different region but smoky-spicy rub.", "category": "spice blend"},
    ],
    "yaji": [
        {"substitute": "suya spice", "note": "Northern Nigerian grill spice mix.", "category": "spice blend"},
        {"substitute": "chili powder + ginger", "note": "Simple dry rub fallback.", "category": "spice blend"},
    ],
    "locust bean": [
        {"substitute": "miso", "note": "1 tsp miso per tbsp iru.", "category": "seasoning"},
        {"substitute": "fermented soy", "note": "Watch salt levels.", "category": "seasoning"},
    ],
    "iru": [
        {"substitute": "miso", "note": "1 tsp miso per tbsp iru.", "category": "seasoning"},
        {"substitute": "locust bean", "note": "Same product, different name.", "category": "seasoning"},
    ],
    "maggi": [
        {"substitute": "bouillon cube", "note": "Same quantity.", "category": "seasoning"},
        {"substitute": "homemade stock concentrate", "note": "Reduce stock until intense.", "category": "seasoning"},
    ],
    "seasoning cube": [
        {"substitute": "bouillon cube", "note": "Direct swap.", "category": "seasoning"},
        {"substitute": "soy sauce + pinch sugar", "note": "Umami boost in a pinch.", "category": "seasoning"},
    ],
    "tomato paste": [
        {"substitute": "canned tomato", "note": "Blend or crush; cook down longer.", "category": "produce"},
        {"substitute": "tomato purée", "note": "Similar intensity; adjust liquid.", "category": "produce"},
    ],
    "fresh tomato": [
        {"substitute": "canned tomato", "note": "Use when tomatoes are out of season.", "category": "produce"},
        {"substitute": "tomato paste", "note": "1 tbsp paste + water per medium tomato.", "category": "produce"},
    ],
    "ginger": [
        {"substitute": "ground ginger", "note": "¼ tsp ground per tsp fresh.", "category": "spice"},
        {"substitute": "galangal", "note": "Sharper; common in coastal dishes.", "category": "spice"},
    ],
    "garlic": [
        {"substitute": "garlic powder", "note": "⅛ tsp powder per clove.", "category": "spice"},
        {"substitute": "shallot", "note": "Milder; use a bit more volume.", "category": "produce"},
    ],
    "onion": [
        {"substitute": "shallot", "note": "Sweeter; use more by volume.", "category": "produce"},
        {"substitute": "onion powder", "note": "1 tsp powder per small onion.", "category": "spice"},
    ],
    "bell pepper": [
        {"substitute": "pimento", "note": "Similar sweetness.", "category": "produce"},
        {"substitute": "capsicum", "note": "Regional name; same use.", "category": "produce"},
    ],
    "scent leaf": [
        {"substitute": "basil", "note": "Closest herb for pepper soup.", "category": "herb"},
        {"substitute": "mint", "note": "Cooler note; use half amount.", "category": "herb"},
    ],
    "bitter leaf": [
        {"substitute": "spinach", "note": "Milder; blanch to reduce bitterness.", "category": "herb"},
        {"substitute": "kale", "note": "Hearty green; parboil first.", "category": "herb"},
    ],
    "utazi": [
        {"substitute": "bitter leaf", "note": "Similar bitter soup greens.", "category": "herb"},
        {"substitute": "arugula", "note": "Peppery bite in salads or garnish.", "category": "herb"},
    ],
    "coconut milk": [
        {"substitute": "coconut cream", "note": "Richer; dilute with water.", "category": "dairy alt"},
        {"substitute": "evaporated milk", "note": "Creamy but less coconut flavour.", "category": "dairy alt"},
    ],
    "curry powder": [
        {"substitute": "turmeric + coriander + cumin", "note": "Simple blend approximation.", "category": "spice blend"},
        {"substitute": "jollof spice", "note": "West African rice/stew blend.", "category": "spice blend"},
    ],
    "turmeric": [
        {"substitute": "saffron", "note": "Pinch for colour only; different flavour.", "category": "spice"},
        {"substitute": "annatto", "note": "Colour without turmeric earthiness.", "category": "spice"},
    ],
    "cumin": [
        {"substitute": "coriander", "note": "Milder citrus note.", "category": "spice"},
        {"substitute": "caraway", "note": "Earthy; use less quantity.", "category": "spice"},
    ],
    "coriander": [
        {"substitute": "cumin", "note": "Warmer; not identical but workable.", "category": "spice"},
        {"substitute": "parsley", "note": "Fresh garnish substitute only.", "category": "herb"},
    ],
    "black pepper": [
        {"substitute": "white pepper", "note": "Milder; same heat level.", "category": "spice"},
        {"substitute": "alligator pepper", "note": "Traditional West African heat.", "category": "spice"},
    ],
    "alligator pepper": [
        {"substitute": "grains of paradise", "note": "Similar aromatic pepper.", "category": "spice"},
        {"substitute": "black pepper", "note": "Easier to find; less floral.", "category": "spice"},
    ],
    "grains of paradise": [
        {"substitute": "alligator pepper", "note": "Close aromatic substitute.", "category": "spice"},
        {"substitute": "black pepper + cardamom", "note": "Pinch of each for complexity.", "category": "spice"},
    ],
    "nutmeg": [
        {"substitute": "mace", "note": "Same fruit; warmer note.", "category": "spice"},
        {"substitute": "cinnamon", "note": "Sweet spice in rice and bakes.", "category": "spice"},
    ],
    "cinnamon": [
        {"substitute": "nutmeg", "note": "Warm spice in savoury rice.", "category": "spice"},
        {"substitute": "clove", "note": "Strong; use sparingly.", "category": "spice"},
    ],
    "clove": [
        {"substitute": "cinnamon", "note": "Milder warm spice.", "category": "spice"},
        {"substitute": "star anise", "note": "Liquorice note in stews.", "category": "spice"},
    ],
    "thyme": [
        {"substitute": "oregano", "note": "Similar dry herb for stews.", "category": "herb"},
        {"substitute": "bay leaf", "note": "Simmer whole; remove before serving.", "category": "herb"},
    ],
    "bay leaf": [
        {"substitute": "thyme", "note": "Earthy soup herb.", "category": "herb"},
        {"substitute": "curry leaf", "note": "Different aroma; common in fusion pots.", "category": "herb"},
    ],
    "black eyed pea": [
        {"substitute": "brown bean", "note": "Similar Nigerian stew bean.", "category": "legume"},
        {"substitute": "kidney bean", "note": "Longer cook; soak overnight.", "category": "legume"},
    ],
    "brown bean": [
        {"substitute": "black eyed pea", "note": "Classic ewa riro bean.", "category": "legume"},
        {"substitute": "pinto bean", "note": "Creamy stew texture.", "category": "legume"},
    ],
    "rice": [
        {"substitute": "jasmine rice", "note": "Fragrant jollof-friendly grain.", "category": "grain"},
        {"substitute": "basmati rice", "note": "Long grain; rinse well.", "category": "grain"},
    ],
    "millet": [
        {"substitute": "sorghum", "note": "Similar ancient grain porridge.", "category": "grain"},
        {"substitute": "couscous", "note": "Quick-cooking grain side.", "category": "grain"},
    ],
    "yam": [
        {"substitute": "sweet potato", "note": "Boil or fry; slightly sweeter.", "category": "produce"},
        {"substitute": "cassava", "note": "Starchy tuber in pottages.", "category": "produce"},
    ],
    "cassava": [
        {"substitute": "yuca", "note": "Same tuber, different label.", "category": "produce"},
        {"substitute": "potato", "note": "Shorter cook; less fibrous.", "category": "produce"},
    ],
    "periwinkle": [
        {"substitute": "snail", "note": "Similar chewy protein in soup.", "category": "protein"},
        {"substitute": "mussel", "note": "Briny seafood in pepper soup.", "category": "protein"},
    ],
    "goat meat": [
        {"substitute": "lamb", "note": "Closest red meat for pepper soup.", "category": "protein"},
        {"substitute": "beef shin", "note": "Long braise for similar texture.", "category": "protein"},
    ],
    "chicken": [
        {"substitute": "guinea fowl", "note": "Gamier traditional bird.", "category": "protein"},
        {"substitute": "turkey wing", "note": "Rich broth for stews.", "category": "protein"},
    ],
    "beef": [
        {"substitute": "goat meat", "note": "Leaner; classic in soups.", "category": "protein"},
        {"substitute": "oxtail", "note": "Collagen-rich stew cut.", "category": "protein"},
    ],
    "palm wine": [
        {"substitute": "white grape juice", "note": "Non-alcoholic stand-in in marinades.", "category": "liquid"},
        {"substitute": "dry sherry", "note": "Small splash in savoury sauces.", "category": "liquid"},
    ],
    "tamarind": [
        {"substitute": "lime juice + sugar", "note": "Sour-sweet balance.", "category": "seasoning"},
        {"substitute": "pomegranate molasses", "note": "Thick sour note.", "category": "seasoning"},
    ],
    "shea butter": [
        {"substitute": "coconut oil", "note": "Fat for skin or rare savoury use.", "category": "fat"},
        {"substitute": "vegetable shortening", "note": "Neutral fat in baking.", "category": "fat"},
    ],
}

SUBSTITUTIONS: dict[str, list[dict]] = {
    normalize_ingredient_name(k): v for k, v in _RAW.items()
}


def get_substitutes(ingredient_name: str) -> list[dict]:
    """Return substitution entries for a normalized ingredient name, or []."""
    key = normalize_ingredient_name(ingredient_name)
    return SUBSTITUTIONS.get(key, [])


def get_substitute_names(ingredient_name: str) -> list[str]:
    """Return substitute names only (for cook_now payloads)."""
    return [entry["substitute"] for entry in get_substitutes(ingredient_name)]


def get_substitutes_for_many(
    ingredient_names: list[str],
) -> dict[str, list[dict]]:
    """Return {normalized_name: substitute entries} for each ingredient."""
    result: dict[str, list[dict]] = {}
    for name in ingredient_names:
        key = normalize_ingredient_name(name)
        result[key] = SUBSTITUTIONS.get(key, [])
    return result


def substitution_names_for_missing(
    missing: list[str],
) -> dict[str, list[str]]:
    """Map each missing ingredient to a list of substitute name strings."""
    out: dict[str, list[str]] = {}
    for name in missing:
        key = normalize_ingredient_name(name)
        if not key:
            continue
        subs = SUBSTITUTIONS.get(key, [])
        if subs:
            out[key] = [entry["substitute"] for entry in subs]
    return out
