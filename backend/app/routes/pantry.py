"""
Pantry routes. Every route is scoped to the authenticated user.

GET    /api/pantry                     full view: 22 catalog items + custom items
POST   /api/pantry                     add stock (idempotent with idempotency_key)
PATCH  /api/pantry/{ingredient_id}     edit quantity / unit / expiry
DELETE /api/pantry/{ingredient_id}     remove an item
POST   /api/pantry/consume             deduct stock after cooking
POST   /api/pantry/reset               remove all of the user's stock
GET    /api/pantry/catalog             the 22 supported vegetables
POST   /api/pantry/predict-expiry      shelf-life estimate for one item
POST   /api/pantry/refresh-all-expiry  re-estimate expiry for every stocked item
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ..database.connection import get_database
from ..middleware.auth_middleware import get_current_user
from ..services.expiry_service import ExpiryService
from ..services.ingredient_catalog import get_catalog, get_catalog_entry, get_catalog_list, normalize_ingredient_name
from ..services.inventory_service import (
    InventoryService,
    normalize_unit,
    parse_quantity_string,
    parse_relative_expiry,
)

router = APIRouter()


# ── Request models ───────────────────────────────────────────────────────

class PantryAddItem(BaseModel):
    """Accepts both the current and the older (receipt) item formats."""
    model_config = ConfigDict(extra="ignore")

    ingredient_id: Optional[str] = Field(None, max_length=80)
    name: Optional[str] = Field(None, max_length=80)
    quantity: Optional[Union[float, int, str]] = None
    unit: Optional[str] = Field(None, max_length=16)
    qty: Optional[str] = Field(None, max_length=32)
    expiry_date: Optional[str] = Field(None, max_length=40)
    expiry: Optional[str] = Field(None, max_length=40)
    category: Optional[str] = Field(None, max_length=40)
    storage_method: Optional[str] = Field(None, max_length=20)
    storage_tip: Optional[str] = Field(None, max_length=200)


class PantryBatchRequest(BaseModel):
    items: List[PantryAddItem] = Field(..., min_length=1, max_length=100)
    idempotency_key: Optional[str] = Field(None, max_length=100)
    source: str = Field("manual", max_length=20)


class PantryUpdateRequest(BaseModel):
    quantity: float = Field(..., ge=0, le=100000)
    unit: str = Field(..., min_length=1, max_length=16)
    expiry_date: Optional[str] = Field(None, max_length=40)  # ISO date; null clears it
    storage_method: Optional[str] = Field(None, max_length=20)


class PredictExpiryRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    category: Optional[str] = Field(None, max_length=40)
    storage_method: Optional[str] = Field(None, max_length=20)


class ConsumeRequest(BaseModel):
    ingredient_id: str = Field(..., max_length=80)
    quantity: float = Field(..., gt=0, le=100000)
    unit: str = Field("pcs", max_length=16)


# ── Helpers ──────────────────────────────────────────────────────────────

def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except (ValueError, TypeError):
        return parse_relative_expiry(raw)


def _resolve_items(items: List[PantryAddItem]) -> List[Dict[str, Any]]:
    """Normalise add-item payloads; estimate expiry for items that lack one
    with a single batched prediction call."""
    resolved: List[Dict[str, Any]] = []
    for item in items:
        raw_ident = (item.ingredient_id or item.name or "").strip()
        if not raw_ident:
            continue
        ingredient_id = normalize_ingredient_name(raw_ident) or raw_ident.lower().replace(" ", "_")

        quantity, unit = None, item.unit or None
        if isinstance(item.quantity, (int, float)) and not isinstance(item.quantity, bool):
            quantity = float(item.quantity)
        elif isinstance(item.quantity, str) and item.quantity.strip():
            quantity, parsed_unit = parse_quantity_string(item.quantity)
            unit = unit or parsed_unit
        if quantity is None and item.qty:
            quantity, parsed_unit = parse_quantity_string(item.qty)
            unit = unit or parsed_unit
        if quantity is None or quantity <= 0:
            quantity = 1.0
        if not unit:
            unit = (get_catalog_entry(ingredient_id) or {}).get("default_unit", "pcs")

        resolved.append({
            "ingredient_id": ingredient_id,
            "name": raw_ident,
            "category": item.category,
            "quantity": float(quantity),
            "unit": normalize_unit(unit),
            "expiry_date": _parse_date(item.expiry_date or item.expiry),
            "storage_method": item.storage_method,
            "storage_tip": item.storage_tip,
            "ai_predicted": False,
        })

    missing = [r for r in resolved if r["expiry_date"] is None]
    if missing:
        preds = ExpiryService.batch_predict_items(
            [{"id": str(i), "name": (get_catalog_entry(r["ingredient_id"]) or {}).get("display_name", r["name"]),
              "category": r["category"]} for i, r in enumerate(missing)]
        )
        for r, p in zip(missing, preds):
            r["expiry_date"] = _parse_date(p.get("expiry_date"))
            r["storage_method"] = r["storage_method"] or p.get("storage_method")
            r["storage_tip"] = r["storage_tip"] or p.get("storage_tip")
            r["ai_predicted"] = bool(p.get("ai_predicted"))
    return resolved


_STATUS_LABEL = {
    "fresh": "Fresh", "use_soon": "Use Soon", "expiring_soon": "Expiring Soon",
    "expired": "Expired", "unknown": "Fresh", "empty": "",
}


def _with_compat_fields(merged: Dict[str, Any]) -> Dict[str, Any]:
    merged["id"] = merged["ingredient_id"]
    merged["name"] = merged["display_name"]
    merged["quantity"] = merged["display_quantity"]
    merged["expiry"] = merged["expiry_display"]
    merged["status"] = _STATUS_LABEL.get(merged.get("expiry_status", "empty"), "Fresh")
    return merged


def build_full_view(database, user_id: str) -> List[Dict[str, Any]]:
    """All 22 catalog items merged with the user's inventory, then custom items."""
    catalog = get_catalog()
    docs = list(database["pantry_items"].find({"user_id": user_id, "ingredient_id": {"$exists": True}}))
    inventory = {d["ingredient_id"]: d for d in docs if d.get("ingredient_id")}

    results = []
    for ingredient_id, entry in sorted(catalog.items(), key=lambda x: x[1]["class_index"]):
        merged = InventoryService._merge_catalog_inventory(entry, inventory.get(ingredient_id))
        results.append(_with_compat_fields(merged))
    for ingredient_id, doc in inventory.items():
        if ingredient_id not in catalog:
            results.append(_with_compat_fields(InventoryService._merge_catalog_inventory({}, doc)))
    return results


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("")
def get_pantry_items(user_id: str = Depends(get_current_user), database=Depends(get_database)):
    return build_full_view(database, user_id)


@router.post("")
def add_pantry_items(payload: PantryBatchRequest, user_id: str = Depends(get_current_user),
                     database=Depends(get_database)):
    resolved = _resolve_items(payload.items)
    if not resolved:
        raise HTTPException(status_code=400, detail="No valid items to add.")
    InventoryService.add_stock_batch(
        db=database, user_id=user_id, items=resolved,
        source=payload.source, idempotency_key=payload.idempotency_key,
    )
    return build_full_view(database, user_id)


@router.get("/catalog")
def get_catalog_endpoint():
    return get_catalog_list()


@router.post("/consume")
def consume_pantry_item(payload: ConsumeRequest, user_id: str = Depends(get_current_user),
                        database=Depends(get_database)):
    try:
        result = InventoryService.remove_stock(
            db=database, user_id=user_id, ingredient_id=payload.ingredient_id,
            quantity=payload.quantity, unit=payload.unit,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    return {"success": True, "ingredient": result}


@router.post("/reset")
def reset_pantry(user_id: str = Depends(get_current_user), database=Depends(get_database)):
    result = database["pantry_items"].delete_many({"user_id": user_id})
    return {"success": True, "deleted": result.deleted_count}


@router.post("/predict-expiry")
def predict_item_expiry(payload: PredictExpiryRequest, user_id: str = Depends(get_current_user)):
    prediction = ExpiryService.predict_single_item(
        name=payload.name, category=payload.category, storage_method=payload.storage_method,
    )
    return {"success": True, "prediction": prediction}


@router.post("/refresh-all-expiry")
def refresh_all_expiry(user_id: str = Depends(get_current_user), database=Depends(get_database)):
    """Re-estimate expiry for every stocked item, counted from when it was added."""
    coll = database["pantry_items"]
    docs = [d for d in coll.find({"user_id": user_id, "ingredient_id": {"$exists": True}}) if d.get("batches")]
    if not docs:
        return build_full_view(database, user_id)

    preds = ExpiryService.batch_predict_items([
        {"id": d["ingredient_id"],
         "name": (get_catalog_entry(d["ingredient_id"]) or {}).get("display_name") or d.get("name") or d["ingredient_id"],
         "category": d.get("category")}
        for d in docs
    ])
    by_id = {p["id"]: p for p in preds}
    now = datetime.utcnow()
    for doc in docs:
        p = by_id.get(doc["ingredient_id"])
        if not p:
            continue
        days = int(p["shelf_life_days"])
        for b in doc["batches"]:
            added = b.get("added_at") if isinstance(b.get("added_at"), datetime) else now
            b["expiry_date"] = added.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days)
            b["storage_method"] = p.get("storage_method", b.get("storage_method"))
            b["storage_tip"] = p.get("storage_tip", b.get("storage_tip", ""))
            b["ai_predicted"] = bool(p.get("ai_predicted"))
        coll.update_one(
            {"_id": doc["_id"], "user_id": user_id},
            {"$set": {"batches": doc["batches"], "updated_at": now,
                      "storage_method": p.get("storage_method"), "storage_tip": p.get("storage_tip", "")}},
        )
    return build_full_view(database, user_id)


@router.patch("/{ingredient_id}")
def update_pantry_item(ingredient_id: str, payload: PantryUpdateRequest,
                       user_id: str = Depends(get_current_user), database=Depends(get_database)):
    expiry = _parse_date(payload.expiry_date) if payload.expiry_date else None
    if payload.expiry_date and expiry is None:
        raise HTTPException(status_code=422, detail="expiry_date must be an ISO date (YYYY-MM-DD).")
    result = InventoryService.set_stock(
        database, user_id, ingredient_id, payload.quantity, payload.unit,
        expiry_date=expiry, storage_method=payload.storage_method,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found in your pantry.")
    return _with_compat_fields(result)


@router.delete("/{ingredient_id}")
def delete_pantry_item(ingredient_id: str, user_id: str = Depends(get_current_user),
                       database=Depends(get_database)):
    if not InventoryService.delete_inventory(database, user_id, ingredient_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found in your pantry.")
    return {"success": True}
