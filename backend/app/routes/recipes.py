"""Recipe recommendations generated from the user's real pantry inventory."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..database.connection import get_database
from ..middleware.auth_middleware import get_current_user
from ..services.gemini_client import GeminiError, GeminiNotConfigured
from ..services.gemini_service import GeminiService
from ..services.ingredient_catalog import normalize_ingredient_name
from ..services.inventory_service import InventoryService

router = APIRouter()

_PRIORITY = {"expired": 0, "expiring_soon": 1, "use_soon": 2, "fresh": 3, "unknown": 4}


class RecipeRequest(BaseModel):
    selected_ingredients: Optional[List[str]] = Field(None, max_length=40)
    servings: int = Field(2, ge=1, le=12)
    max_cooking_time: Optional[int] = Field(None, ge=5, le=600)
    dietary_preferences: List[str] = Field(default_factory=list, max_length=10)
    prioritize_expiring: bool = True
    include_expired: bool = False


@router.post("/recommend")
def recommend_recipes(request: RecipeRequest, user_id: str = Depends(get_current_user),
                      database=Depends(get_database)):
    inventory = [i for i in InventoryService.get_user_inventory(database, user_id) if i.get("in_stock")]
    if not request.include_expired:
        # Never build recipes around food that has already gone off.
        inventory = [i for i in inventory if i.get("expiry_status") != "expired"]

    context = [{
        "name": i["display_name"],
        "ingredient_id": i["ingredient_id"],
        "quantity": i["display_quantity"],
        "expiry_display": i.get("expiry_display", ""),
        "expiry_status": i.get("expiry_status", "unknown"),
    } for i in inventory]

    if request.selected_ingredients:
        wanted = {normalize_ingredient_name(s) or s.strip().lower() for s in request.selected_ingredients}
        context = [c for c in context if c["ingredient_id"] in wanted or c["name"].lower() in wanted]

    if not context:
        return {"recipes": [], "pantry_items_used": 0, "pantry_context": [],
                "message": "Add some items to your pantry to get recipe suggestions."}

    if request.prioritize_expiring:
        context.sort(key=lambda c: _PRIORITY.get(c["expiry_status"], 5))

    try:
        recipes = GeminiService.recommend_recipes(
            ingredients=[c["name"] for c in context], pantry_context=context,
            servings=request.servings, max_cooking_time=request.max_cooking_time,
            dietary_preferences=request.dietary_preferences,
        )
    except GeminiNotConfigured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Recipe suggestions are not configured on the server.")
    except GeminiError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    available = {c["name"].lower() for c in context}
    for r in recipes:
        r["available_ingredients"] = [i for i in r["ingredients_used"] if i.lower() in available]
    return {"recipes": recipes, "pantry_items_used": len(context), "pantry_context": context}
