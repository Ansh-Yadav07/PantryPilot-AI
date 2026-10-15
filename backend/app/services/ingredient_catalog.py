"""
Canonical ingredient catalog for PantryPilot AI.

Contains the 22 YOLO-detectable vegetable classes with:
- Canonical IDs matching YOLO class names
- Display names, categories, emojis
- Explicit alias maps for normalization
- Idempotent MongoDB seeding

All entry points (scanner, receipt, manual add, recipe matching) must
use normalize_ingredient_name() to resolve names to canonical IDs.
"""

from typing import Optional, Dict, List, Any
from datetime import datetime


# ── Canonical Catalog ────────────────────────────────────────────────────

CATALOG: Dict[str, Dict[str, Any]] = {
    "cucumber": {
        "id": "cucumber",
        "class_index": 0,
        "display_name": "Cucumber",
        "category": "Vegetables",
        "emoji": "🥒",
        "default_unit": "pcs",
        "image_asset": "cucumber.png",
    },
    "tomato": {
        "id": "tomato",
        "class_index": 1,
        "display_name": "Tomato",
        "category": "Vegetables",
        "emoji": "🍅",
        "default_unit": "pcs",
        "image_asset": "tomato.png",
    },
    "green_beans": {
        "id": "green_beans",
        "class_index": 2,
        "display_name": "Green Beans",
        "category": "Vegetables",
        "emoji": "🫛",
        "default_unit": "g",
        "image_asset": "green_beans.png",
    },
    "lemon": {
        "id": "lemon",
        "class_index": 3,
        "display_name": "Lemon",
        "category": "Vegetables",
        "emoji": "🍋",
        "default_unit": "pcs",
        "image_asset": "lemon.png",
    },
    "eggplant": {
        "id": "eggplant",
        "class_index": 4,
        "display_name": "Eggplant",
        "category": "Vegetables",
        "emoji": "🍆",
        "default_unit": "pcs",
        "image_asset": "eggplant.png",
    },
    "green_chilli": {
        "id": "green_chilli",
        "class_index": 5,
        "display_name": "Green Chilli",
        "category": "Vegetables",
        "emoji": "🌶️",
        "default_unit": "pcs",
        "image_asset": "green_chilli.png",
    },
    "turnip": {
        "id": "turnip",
        "class_index": 6,
        "display_name": "Turnip",
        "category": "Vegetables",
        "emoji": "🥕",
        "default_unit": "pcs",
        "image_asset": "turnip.png",
    },
    "coriander": {
        "id": "coriander",
        "class_index": 7,
        "display_name": "Coriander",
        "category": "Vegetables",
        "emoji": "🥬",
        "default_unit": "g",
        "image_asset": "coriander.png",
    },
    "pumpkin": {
        "id": "pumpkin",
        "class_index": 8,
        "display_name": "Pumpkin",
        "category": "Vegetables",
        "emoji": "🎃",
        "default_unit": "pcs",
        "image_asset": "pumpkin.png",
    },
    "potato": {
        "id": "potato",
        "class_index": 9,
        "display_name": "Potato",
        "category": "Vegetables",
        "emoji": "🥔",
        "default_unit": "pcs",
        "image_asset": "potato.png",
    },
    "cauliflower": {
        "id": "cauliflower",
        "class_index": 10,
        "display_name": "Cauliflower",
        "category": "Vegetables",
        "emoji": "🥦",
        "default_unit": "pcs",
        "image_asset": "cauliflower.png",
    },
    "green_papaya": {
        "id": "green_papaya",
        "class_index": 11,
        "display_name": "Green Papaya",
        "category": "Vegetables",
        "emoji": "🥭",
        "default_unit": "pcs",
        "image_asset": "green_papaya.png",
    },
    "bitter_gourd": {
        "id": "bitter_gourd",
        "class_index": 12,
        "display_name": "Bitter Gourd",
        "category": "Vegetables",
        "emoji": "🥒",
        "default_unit": "pcs",
        "image_asset": "bitter_gourd.png",
    },
    "carrot": {
        "id": "carrot",
        "class_index": 13,
        "display_name": "Carrot",
        "category": "Vegetables",
        "emoji": "🥕",
        "default_unit": "pcs",
        "image_asset": "carrot.png",
    },
    "bottle_gourd": {
        "id": "bottle_gourd",
        "class_index": 14,
        "display_name": "Bottle Gourd",
        "category": "Vegetables",
        "emoji": "🥒",
        "default_unit": "pcs",
        "image_asset": "bottle_gourd.png",
    },
    "capsicum": {
        "id": "capsicum",
        "class_index": 15,
        "display_name": "Capsicum",
        "category": "Vegetables",
        "emoji": "🫑",
        "default_unit": "pcs",
        "image_asset": "capsicum.png",
    },
    "beetroot": {
        "id": "beetroot",
        "class_index": 16,
        "display_name": "Beetroot",
        "category": "Vegetables",
        "emoji": "🟣",
        "default_unit": "pcs",
        "image_asset": "beetroot.png",
    },
    "cabbage": {
        "id": "cabbage",
        "class_index": 17,
        "display_name": "Cabbage",
        "category": "Vegetables",
        "emoji": "🥬",
        "default_unit": "pcs",
        "image_asset": "cabbage.png",
    },
    "spring_onion": {
        "id": "spring_onion",
        "class_index": 18,
        "display_name": "Spring Onion",
        "category": "Vegetables",
        "emoji": "🧅",
        "default_unit": "pcs",
        "image_asset": "spring_onion.png",
    },
    "snake_gourd": {
        "id": "snake_gourd",
        "class_index": 19,
        "display_name": "Snake Gourd",
        "category": "Vegetables",
        "emoji": "🥒",
        "default_unit": "pcs",
        "image_asset": "snake_gourd.png",
    },
    "radish": {
        "id": "radish",
        "class_index": 20,
        "display_name": "Radish",
        "category": "Vegetables",
        "emoji": "🥕",
        "default_unit": "pcs",
        "image_asset": "radish.png",
    },
    "green_banana": {
        "id": "green_banana",
        "class_index": 21,
        "display_name": "Green Banana",
        "category": "Vegetables",
        "emoji": "🍌",
        "default_unit": "pcs",
        "image_asset": "green_banana.png",
    },
}


# ── Alias Map ────────────────────────────────────────────────────────────
# Explicit alias-to-canonical-ID mapping.
# Every known spelling, plural, and regional name maps to one canonical ID.

_EXPLICIT_ALIASES: Dict[str, str] = {
    # cucumber
    "cucumber": "cucumber", "cucumbers": "cucumber", "kheera": "cucumber",
    "khira": "cucumber",
    # tomato
    "tomato": "tomato", "tomatoes": "tomato", "tamatar": "tomato",
    "cherry tomato": "tomato", "cherry tomatoes": "tomato",
    # green_beans
    "green beans": "green_beans", "green_beans": "green_beans",
    "beans": "green_beans", "french beans": "green_beans",
    "string beans": "green_beans",
    # lemon
    "lemon": "lemon", "lemons": "lemon", "nimbu": "lemon",
    "lime": "lemon", "limes": "lemon",
    # eggplant
    "eggplant": "eggplant", "eggplants": "eggplant",
    "aubergine": "eggplant", "brinjal": "eggplant",
    "baingan": "eggplant", "baigan": "eggplant",
    # green_chilli
    "green chilli": "green_chilli", "green chili": "green_chilli",
    "green chillies": "green_chilli", "green chilies": "green_chilli",
    "green_chilli": "green_chilli", "hari mirch": "green_chilli",
    "chilli": "green_chilli", "chili": "green_chilli",
    "green pepper": "green_chilli",
    # turnip
    "turnip": "turnip", "turnips": "turnip", "shalgam": "turnip",
    # coriander
    "coriander": "coriander", "cilantro": "coriander",
    "dhania": "coriander", "coriander leaves": "coriander",
    # pumpkin
    "pumpkin": "pumpkin", "pumpkins": "pumpkin", "kaddu": "pumpkin",
    # potato
    "potato": "potato", "potatoes": "potato", "aloo": "potato",
    # cauliflower
    "cauliflower": "cauliflower", "cauliflowers": "cauliflower",
    "gobi": "cauliflower", "phool gobi": "cauliflower",
    "gobhi": "cauliflower",
    # green_papaya
    "green papaya": "green_papaya", "green_papaya": "green_papaya",
    "raw papaya": "green_papaya", "kacha papaya": "green_papaya",
    # bitter_gourd
    "bitter gourd": "bitter_gourd", "bitter_gourd": "bitter_gourd",
    "bitter melon": "bitter_gourd", "karela": "bitter_gourd",
    # carrot
    "carrot": "carrot", "carrots": "carrot", "gajar": "carrot",
    # bottle_gourd
    "bottle gourd": "bottle_gourd", "bottle_gourd": "bottle_gourd",
    "lauki": "bottle_gourd", "ghiya": "bottle_gourd",
    "calabash": "bottle_gourd", "dudhi": "bottle_gourd",
    # capsicum
    "capsicum": "capsicum", "capsicums": "capsicum",
    "bell pepper": "capsicum", "bell peppers": "capsicum",
    "shimla mirch": "capsicum",
    # beetroot
    "beetroot": "beetroot", "beetroots": "beetroot",
    "beet": "beetroot", "beets": "beetroot",
    "chukandar": "beetroot",
    # cabbage
    "cabbage": "cabbage", "cabbages": "cabbage",
    "patta gobhi": "cabbage", "patta gobi": "cabbage",
    # spring_onion
    "spring onion": "spring_onion", "spring onions": "spring_onion",
    "spring_onion": "spring_onion",
    "green onion": "spring_onion", "green onions": "spring_onion",
    "scallion": "spring_onion", "scallions": "spring_onion",
    # snake_gourd
    "snake gourd": "snake_gourd", "snake_gourd": "snake_gourd",
    "chichinda": "snake_gourd", "padwal": "snake_gourd",
    # radish
    "radish": "radish", "radishes": "radish",
    "mooli": "radish", "muli": "radish", "daikon": "radish",
    # green_banana
    "green banana": "green_banana", "green bananas": "green_banana",
    "green_banana": "green_banana",
    "raw banana": "green_banana", "raw bananas": "green_banana",
    "plantain": "green_banana", "kaccha kela": "green_banana",
}


def normalize_ingredient_name(name: str) -> Optional[str]:
    """
    Normalize any ingredient name/alias to a canonical ingredient ID.

    Uses a strict alias map. Falls back to simple heuristics (underscores,
    trailing 's' removal) only when the alias map has no match.

    Returns the canonical ID (e.g., "tomato") or None if unrecognized.
    """
    if not name or not name.strip():
        return None

    cleaned = name.strip().lower().replace("_", " ")

    # 1. Direct alias match
    if cleaned in _EXPLICIT_ALIASES:
        return _EXPLICIT_ALIASES[cleaned]

    # 2. Try with underscores (YOLO class format)
    underscored = cleaned.replace(" ", "_")
    if underscored in _EXPLICIT_ALIASES:
        return _EXPLICIT_ALIASES[underscored]

    # 3. Try removing trailing 's' (only for known base words)
    if cleaned.endswith("s") and len(cleaned) > 3:
        singular = cleaned[:-1]
        if singular in _EXPLICIT_ALIASES:
            return _EXPLICIT_ALIASES[singular]

    # 4. Try removing trailing 'es'
    if cleaned.endswith("es") and len(cleaned) > 4:
        singular = cleaned[:-2]
        if singular in _EXPLICIT_ALIASES:
            return _EXPLICIT_ALIASES[singular]

    # 5. Check if it's a direct catalog ID
    if cleaned.replace(" ", "_") in CATALOG:
        return cleaned.replace(" ", "_")

    return None


def get_catalog_entry(ingredient_id: str) -> Optional[Dict[str, Any]]:
    """Get a single catalog entry by canonical ID."""
    return CATALOG.get(ingredient_id)


def get_catalog() -> Dict[str, Dict[str, Any]]:
    """Get the full ingredient catalog dict."""
    return CATALOG


def get_catalog_list() -> List[Dict[str, Any]]:
    """Get all catalog entries as a list, ordered by class_index."""
    return sorted(CATALOG.values(), key=lambda x: x["class_index"])


def seed_catalog(db) -> Dict[str, Any]:
    """
    Idempotently seed the ingredient_catalog collection in MongoDB.

    Uses upsert on 'id' field to avoid duplicates. Safe to call repeatedly.

    Returns: {"seeded": int, "existing": int, "total": int}
    """
    collection = db["ingredient_catalog"]
    seeded = 0
    existing = 0

    for ingredient_id, entry in CATALOG.items():
        doc = {
            **entry,
            "updated_at": datetime.utcnow(),
        }
        result = collection.update_one(
            {"id": ingredient_id},
            {"$set": doc, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
        )
        if result.upserted_id:
            seeded += 1
        else:
            existing += 1

    # Ensure unique index on 'id'
    collection.create_index("id", unique=True)

    return {"seeded": seeded, "existing": existing, "total": len(CATALOG)}


def format_display_name(class_name: str) -> str:
    """Convert YOLO class name to display name. e.g., 'green_beans' -> 'Green Beans'."""
    entry = CATALOG.get(class_name)
    if entry:
        return entry["display_name"]
    return class_name.replace("_", " ").title()
