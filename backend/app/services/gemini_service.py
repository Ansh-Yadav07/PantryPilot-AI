"""
Gemini-powered receipt extraction and recipe recommendations.

No fabricated fallbacks: if Gemini is unavailable the caller gets a
GeminiError / GeminiNotConfigured and the API responds with a clear error.
"""

import logging
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import gemini_client
from .gemini_client import GeminiError
from .ingredient_catalog import get_catalog_entry, normalize_ingredient_name
from .mealdb_service import MealDBService

logger = logging.getLogger("pantrypilot.gemini_service")

RECEIPT_PROMPT = """You are reading a photo of a grocery store receipt.
Extract ONLY what is printed on the receipt. Never guess or invent values: if a
value is not legible or not present, use null.

Return a JSON object with exactly these keys:
{
  "is_receipt": true or false (false if the image is not a shopping receipt),
  "store_name": string or null,
  "purchase_date": "YYYY-MM-DD" or null,
  "currency": ISO 4217 code such as "INR" or "USD", or null,
  "total": number or null (the final amount paid),
  "items": [
    {
      "name": string (clean product name, e.g. "Tomato" not "TOMATO LOOSE 1KG"),
      "quantity": number or null,
      "unit": one of "kg", "g", "l", "ml", "pcs", "pack", or null,
      "price": number or null (line total for this item),
      "category": one of "Vegetables", "Fruits", "Dairy", "Bakery & Grains",
                  "Meat & Seafood", "Snacks & Beverages", "Pantry Staples",
                  "Household", "Other"
    }
  ]
}
Only include purchased products in "items" (skip taxes, discounts, totals,
bags, and payment lines)."""

_ALLOWED_UNITS = {"kg", "g", "l", "ml", "pcs", "pack"}


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def _clean_receipt(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, list):  # tolerate a bare item list
        raw = {"is_receipt": True, "items": raw}
    if not isinstance(raw, dict):
        raise GeminiError("The AI service returned an unexpected receipt format.")

    items: List[Dict[str, Any]] = []
    for it in raw.get("items") or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        unit = str(it.get("unit") or "").strip().lower() or None
        if unit in ("litre", "liter", "ltr"):
            unit = "l"
        if unit not in _ALLOWED_UNITS:
            unit = None
        qty = _num(it.get("quantity"))
        item: Dict[str, Any] = {
            "name": name[:80],
            "quantity": qty if qty and qty > 0 else None,
            "unit": unit,
            "price": _num(it.get("price")),
            "category": str(it.get("category") or "Other")[:40],
        }
        iid = normalize_ingredient_name(name)
        if iid:
            entry = get_catalog_entry(iid) or {}
            item["ingredient_id"] = iid
            item["emoji"] = entry.get("emoji")
            item["category"] = entry.get("category", item["category"])
        items.append(item)

    date = raw.get("purchase_date")
    try:
        date = datetime.strptime(str(date), "%Y-%m-%d").strftime("%Y-%m-%d") if date else None
    except ValueError:
        date = None

    items_total = sum(i["price"] for i in items if i["price"] is not None)
    return {
        "is_receipt": bool(raw.get("is_receipt", True)),
        "store_name": (str(raw["store_name"]).strip()[:80] if raw.get("store_name") else None),
        "purchase_date": date,
        "currency": (str(raw["currency"]).upper()[:3] if raw.get("currency") else None),
        "total": _num(raw.get("total")),
        "items_total": round(items_total, 2) if items else None,
        "items": items,
    }


RECIPE_STYLES = [
    "North Indian home-style sabzi or curry",
    "South Indian style (poriyal, kootu, sambar or thoran)",
    "dal or lentil-based dish",
    "rice dish (pulao, khichdi or fried rice)",
    "soup or light stew",
    "salad or raita",
    "stuffed or roasted vegetables",
    "quick stir-fry",
    "street-food style snack (tikki, pakora, chaat)",
    "flatbread, paratha or wrap filling",
    "Mediterranean-inspired dish",
    "East Asian-inspired dish",
    "baked or one-pot dish",
    "chutney, pickle-style side or dip",
]


def _norm(name: str) -> str:
    return " ".join(str(name).lower().replace("&", "and").split())


class GeminiService:
    @staticmethod
    def process_receipt_image(image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        raw = gemini_client.generate_json(
            [gemini_client.image_part(image_bytes, mime_type), RECEIPT_PROMPT],
            timeout=60.0,
            temperature=0.0,
        )
        return _clean_receipt(raw)

    @staticmethod
    def recommend_recipes(
        ingredients: List[str],
        pantry_context: Optional[List[Dict[str, Any]]] = None,
        servings: int = 2,
        max_cooking_time: Optional[int] = None,
        dietary_preferences: Optional[List[str]] = None,
        count: int = 3,
        exclude: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        pantry_lines = []
        for item in pantry_context or [{"name": n} for n in ingredients]:
            line = f"- {item['name']}"
            if item.get("quantity"):
                line += f" ({item['quantity']})"
            exp = item.get("expiry_display", "")
            if exp and exp not in ("No expiry set", "Not in pantry"):
                line += f" [expiry: {exp}]"
            pantry_lines.append(line)

        constraints = []
        if max_cooking_time:
            constraints.append(f"- Total time must not exceed {max_cooking_time} minutes.")
        if dietary_preferences:
            constraints.append(f"- Dietary requirements: {', '.join(dietary_preferences)}.")

        # Steer each request towards different cooking styles, so asking again
        # gives genuinely new ideas instead of the same top-probability dishes.
        styles = random.sample(RECIPE_STYLES, k=min(count, len(RECIPE_STYLES)))
        style_text = "; ".join(f"recipe {i + 1}: {s}" for i, s in enumerate(styles))
        exclude = [e.strip() for e in (exclude or []) if e and e.strip()][:30]
        exclude_text = ("\nThe user has already seen these recipes. Do NOT suggest them or close "
                        "variations of them (same main ingredients cooked the same way):\n"
                        + "\n".join(f"- {e}" for e in exclude)) if exclude else ""

        prompt = f"""You are an experienced home-cooking chef.

The user's pantry contains:
{chr(10).join(pantry_lines)}

Servings: {servings}
{chr(10).join(constraints)}

Suggest {count} realistic recipes that use PRIMARILY these pantry ingredients,
giving priority to items that expire soonest. Assume only basic staples (salt,
pepper, oil, water) are available beyond the list; anything else goes in
missing_ingredients.

Make the recipes clearly different from each other: build each one around a
different main pantry ingredient where possible, and use these styles —
{style_text}.{exclude_text}

Return a JSON array; each element has exactly these keys:
- "name": string
- "description": one sentence
- "ingredients_used": array of pantry ingredient names used (from the list above)
- "missing_ingredients": array of ingredients the user must buy
- "prep_time_minutes": integer (total time)
- "servings": integer
- "difficulty": "Easy" | "Medium" | "Hard"
- "calories": string, approximate per serving, e.g. "350 kcal"
- "steps": array of strings, each one clear cooking step"""

        parsed = gemini_client.generate_json([prompt], timeout=60.0, temperature=1.0)
        if isinstance(parsed, dict):
            parsed = parsed.get("recipes") or [parsed]
        if not isinstance(parsed, list):
            raise GeminiError("The AI service returned an unexpected recipe format.")

        recipes: List[Dict[str, Any]] = []
        for r in parsed:
            if not isinstance(r, dict) or not r.get("name"):
                continue
            steps = [str(s).strip() for s in (r.get("steps") or []) if str(s).strip()]
            if not steps and r.get("instructions"):
                steps = [s.strip() for s in str(r["instructions"]).split("\n") if s.strip()]
            minutes = r.get("prep_time_minutes")
            try:
                minutes = int(minutes) if minutes is not None else None
            except (TypeError, ValueError):
                minutes = None
            recipe = {
                "name": str(r["name"]).strip(),
                "description": str(r.get("description") or "").strip(),
                "ingredients_used": [str(i) for i in (r.get("ingredients_used") or [])],
                "missing_ingredients": [str(i) for i in (r.get("missing_ingredients") or [])],
                "prep_time_minutes": minutes,
                "prep_time": f"{minutes} min" if minutes else "",
                "servings": r.get("servings") or servings,
                "difficulty": r.get("difficulty") or "",
                "calories": str(r.get("calories") or ""),
                "steps": steps,
                "instructions": "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps)),
                "source": "gemini",
            }
            recipes.append(recipe)

        # Only attach a photo when TheMealDB has the *same* dish; never
        # substitute another recipe's instructions or a stock image.
        with ThreadPoolExecutor(max_workers=4) as pool:
            metas = list(pool.map(lambda r: MealDBService.exact_match(r["name"]), recipes))
        for recipe, meta in zip(recipes, metas):
            recipe["image_url"] = meta.get("image_url") if meta else None
            recipe["video_url"] = meta.get("video_url") if meta else None

        seen = {_norm(e) for e in exclude}
        fresh = [r for r in recipes if _norm(r["name"]) not in seen]
        recipes = fresh or recipes
        if not recipes:
            raise GeminiError("The AI service did not return any usable recipes. Please try again.")
        return recipes
