"""
ExpiryService — shelf-life / expiry-date estimation.

Uses Gemini when available. When it is not, falls back to a fixed table of
typical refrigerated shelf lives; such results are flagged `ai_predicted=False`
so the UI can label them as estimates rather than AI predictions.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import gemini_client
from .gemini_client import GeminiError, GeminiNotConfigured

logger = logging.getLogger("pantrypilot.expiry")

# Typical shelf life in days (refrigerated where applicable).
DEFAULT_SHELF_LIFE_DAYS = {
    # 22 detectable vegetables
    "cucumber": 7, "tomato": 7, "green beans": 6, "green_beans": 6, "lemon": 21,
    "eggplant": 6, "green chilli": 10, "green_chilli": 10, "turnip": 14,
    "coriander": 5, "pumpkin": 60, "potato": 28, "cauliflower": 7,
    "green papaya": 7, "green_papaya": 7, "bitter gourd": 5, "bitter_gourd": 5,
    "carrot": 21, "bottle gourd": 7, "bottle_gourd": 7, "capsicum": 10,
    "beetroot": 21, "cabbage": 21, "spring onion": 7, "spring_onion": 7,
    "snake gourd": 5, "snake_gourd": 5, "radish": 14, "green banana": 7,
    "green_banana": 7,
    # common groceries
    "milk": 7, "egg": 21, "yogurt": 12, "curd": 5, "paneer": 5, "cheese": 21,
    "butter": 60, "bread": 5, "onion": 30, "garlic": 60, "ginger": 21,
    "spinach": 5, "lettuce": 6, "apple": 20, "banana": 5, "orange": 14,
    "chicken": 2, "fish": 2, "mutton": 3, "beef": 3, "rice": 365, "flour": 180,
    "atta": 180, "dal": 365, "lentil": 365, "pasta": 365, "sugar": 730, "salt": 730,
    "oil": 365,
}


def _baseline_days(name: str) -> int:
    lower = name.lower()
    if lower in DEFAULT_SHELF_LIFE_DAYS:
        return DEFAULT_SHELF_LIFE_DAYS[lower]
    for key, days in DEFAULT_SHELF_LIFE_DAYS.items():
        if key in lower:
            return days
    return 7


def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _baseline(name: str, ref: datetime) -> Dict[str, Any]:
    days = _baseline_days(name)
    return {
        "shelf_life_days": days,
        "expiry_date": (_start_of_day(ref) + timedelta(days=days)).isoformat(),
        "storage_method": "refrigerator" if days <= 21 else "pantry",
        "storage_tip": "",
        "ai_predicted": False,
    }


def _clamp_days(value: Any) -> Optional[int]:
    try:
        return max(1, min(int(value), 730))
    except (TypeError, ValueError):
        return None


class ExpiryService:
    @classmethod
    def predict_single_item(cls, name: str, category: Optional[str] = None,
                            storage_method: Optional[str] = None,
                            purchase_date: Optional[datetime] = None) -> Dict[str, Any]:
        result = cls.batch_predict_items(
            [{"id": "item", "name": name, "category": category, "storage_method": storage_method}],
            reference_date=purchase_date,
        )
        out = dict(result[0])
        out.pop("id", None)
        return out

    @classmethod
    def batch_predict_items(cls, items: List[Dict[str, Any]],
                            reference_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Predict expiry for many items with a single Gemini call."""
        if not items:
            return []
        ref = reference_date or datetime.utcnow()
        clean = [{
            "id": str(it.get("id") or it.get("ingredient_id") or it.get("name")),
            "name": str(it.get("display_name") or it.get("name") or "").strip()[:80],
            "category": str(it.get("category") or "Food"),
        } for it in items]

        predictions: Dict[str, Dict[str, Any]] = {}
        if gemini_client.is_configured():
            prompt = f"""You are a food-safety expert. For each grocery item, estimate the
typical shelf life in days from purchase when stored the recommended way, the
best storage method, and one short practical storage tip.

Items: {clean}

Return a JSON array with one object per item:
{{"id": "<same id>", "shelf_life_days": <integer>,
  "storage_method": "refrigerator" | "pantry" | "freezer",
  "storage_tip": "<one sentence>"}}"""
            try:
                parsed = gemini_client.generate_json([prompt], timeout=25.0, temperature=0.0)
                if isinstance(parsed, list):
                    predictions = {str(p.get("id")): p for p in parsed if isinstance(p, dict)}
            except (GeminiError, GeminiNotConfigured) as e:
                logger.info("Expiry prediction falling back to baseline table: %s", e)

        results = []
        for it, c in zip(items, clean):
            pred = predictions.get(c["id"])
            days = _clamp_days(pred.get("shelf_life_days")) if pred else None
            if days is None:
                out = _baseline(c["name"], ref)
            else:
                method = pred.get("storage_method")
                out = {
                    "shelf_life_days": days,
                    "expiry_date": (_start_of_day(ref) + timedelta(days=days)).isoformat(),
                    "storage_method": method if method in ("refrigerator", "pantry", "freezer") else "refrigerator",
                    "storage_tip": str(pred.get("storage_tip") or "")[:200],
                    "ai_predicted": True,
                }
            results.append({**it, "id": c["id"], **out})
        return results
