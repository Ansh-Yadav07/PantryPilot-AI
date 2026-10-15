"""
Shopping list — persisted per user.

GET    /api/shopping                list + suggestions from the pantry
POST   /api/shopping                add an item (deduplicates open items by name)
PATCH  /api/shopping/{item_id}      update name / quantity / checked
DELETE /api/shopping/{item_id}      remove an item
POST   /api/shopping/clear-checked  remove all checked items
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..database.connection import get_database
from ..middleware.auth_middleware import get_current_user
from ..services.ingredient_catalog import get_catalog_entry, normalize_ingredient_name
from ..services.inventory_service import InventoryService

router = APIRouter()
COLLECTION = "shopping_items"


class ShoppingItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    quantity: Optional[str] = Field(None, max_length=40)
    category: Optional[str] = Field(None, max_length=40)
    source: str = Field("manual", max_length=20)


class ShoppingItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    quantity: Optional[str] = Field(None, max_length=40)
    checked: Optional[bool] = None


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "quantity": doc.get("quantity") or "",
        "category": doc.get("category") or "Other",
        "emoji": doc.get("emoji"),
        "ingredient_id": doc.get("ingredient_id"),
        "checked": bool(doc.get("checked")),
        "source": doc.get("source", "manual"),
    }


def _oid(item_id: str) -> ObjectId:
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return ObjectId(item_id)


def ensure_indexes(db) -> None:
    db[COLLECTION].create_index([("user_id", 1), ("checked", 1), ("created_at", -1)])


@router.get("")
def get_shopping_list(user_id: str = Depends(get_current_user), database=Depends(get_database)):
    docs = list(database[COLLECTION].find({"user_id": user_id}).sort([("checked", 1), ("created_at", -1)]))
    items = [_serialize(d) for d in docs]
    open_names = {i["name"].lower() for i in items if not i["checked"]}

    suggestions = []
    for inv in InventoryService.get_user_inventory(database, user_id):
        if inv.get("expiry_status") in ("expired", "expiring_soon") and inv["display_name"].lower() not in open_names:
            reason = "Expired" if inv["expiry_status"] == "expired" else "Running out soon"
            suggestions.append({"name": inv["display_name"], "ingredient_id": inv["ingredient_id"],
                                "emoji": inv.get("emoji"), "category": inv.get("category"), "reason": reason})
    return {"items": items, "suggestions": suggestions}


@router.post("", status_code=201)
def add_shopping_item(payload: ShoppingItemCreate, user_id: str = Depends(get_current_user),
                      database=Depends(get_database)):
    name = payload.name.strip()
    existing = database[COLLECTION].find_one({
        "user_id": user_id, "checked": False,
        "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
    })
    if existing:
        return _serialize(existing)
    iid = normalize_ingredient_name(name)
    entry = get_catalog_entry(iid) if iid else None
    now = datetime.utcnow()
    doc = {
        "user_id": user_id, "name": (entry or {}).get("display_name", name),
        "quantity": (payload.quantity or "").strip(),
        "category": payload.category or (entry or {}).get("category") or "Other",
        "emoji": (entry or {}).get("emoji"), "ingredient_id": iid,
        "checked": False, "source": payload.source, "created_at": now, "updated_at": now,
    }
    doc["_id"] = database[COLLECTION].insert_one(doc).inserted_id
    return _serialize(doc)


@router.patch("/{item_id}")
def update_shopping_item(item_id: str, payload: ShoppingItemUpdate, user_id: str = Depends(get_current_user),
                         database=Depends(get_database)):
    updates = payload.model_dump(exclude_none=True)
    if "name" in updates:
        updates["name"] = updates["name"].strip()
    updates["updated_at"] = datetime.utcnow()
    doc = database[COLLECTION].find_one_and_update(
        {"_id": _oid(item_id), "user_id": user_id}, {"$set": updates}, return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return _serialize(doc)


@router.delete("/{item_id}")
def delete_shopping_item(item_id: str, user_id: str = Depends(get_current_user), database=Depends(get_database)):
    res = database[COLLECTION].delete_one({"_id": _oid(item_id), "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return {"success": True}


@router.post("/clear-checked")
def clear_checked(user_id: str = Depends(get_current_user), database=Depends(get_database)):
    res = database[COLLECTION].delete_many({"user_id": user_id, "checked": True})
    return {"success": True, "deleted": res.deleted_count}
