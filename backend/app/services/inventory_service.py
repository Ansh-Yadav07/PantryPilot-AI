"""
Shared inventory service for PantryPilot AI.

All pantry inventory mutations flow through this service:
- Vegetable scanner confirmations
- Receipt scanner confirmations
- Manual additions
- Recipe consumption deductions

Provides:
- Atomic MongoDB updates
- Unit compatibility checking and conversion
- Batch support (different expiry dates)
- Idempotency protection
- Canonical ingredient validation
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from pymongo.errors import DuplicateKeyError
from .ingredient_catalog import normalize_ingredient_name, get_catalog, get_catalog_entry


# ── Unit System ──────────────────────────────────────────────────────────

UNIT_GROUPS: Dict[str, Dict[str, float]] = {
    "weight": {"g": 1.0, "kg": 1000.0},
    "volume": {"ml": 1.0, "l": 1000.0},
    "count": {"pcs": 1.0, "pieces": 1.0, "piece": 1.0},
    "pack": {"pack": 1.0, "packs": 1.0},
}

UNIT_ALIASES: Dict[str, str] = {
    "gram": "g", "grams": "g",
    "kilogram": "kg", "kilograms": "kg",
    "milliliter": "ml", "milliliters": "ml",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "piece": "pcs", "pieces": "pcs", "pc": "pcs",
    "pack": "pack", "packs": "pack",
    "bunch": "pcs", "bunches": "pcs",
}

# Preferred display unit per group (use larger unit when quantity is large)
PREFERRED_UNITS: Dict[str, List[Tuple[str, float]]] = {
    "weight": [("kg", 1000.0), ("g", 1.0)],
    "volume": [("l", 1000.0), ("ml", 1.0)],
    "count": [("pcs", 1.0)],
    "pack": [("pack", 1.0)],
}


def normalize_unit(unit: str) -> str:
    """Normalize a unit string to its canonical form."""
    cleaned = unit.strip().lower()
    return UNIT_ALIASES.get(cleaned, cleaned)


def get_unit_group(unit: str) -> Optional[str]:
    """Get the compatibility group for a unit."""
    normalized = normalize_unit(unit)
    for group_name, units in UNIT_GROUPS.items():
        if normalized in units:
            return group_name
    return None


def units_compatible(unit_a: str, unit_b: str) -> bool:
    """Check if two units can be combined (same group)."""
    group_a = get_unit_group(unit_a)
    group_b = get_unit_group(unit_b)
    if group_a is None or group_b is None:
        return False
    return group_a == group_b


def convert_to_base(quantity: float, unit: str) -> Tuple[float, str]:
    """Convert quantity to base unit of its group. Returns (base_quantity, group_name)."""
    normalized = normalize_unit(unit)
    for group_name, units in UNIT_GROUPS.items():
        if normalized in units:
            factor = units[normalized]
            return quantity * factor, group_name
    return quantity, "unknown"


def convert_from_base(base_quantity: float, group_name: str) -> Tuple[float, str]:
    """Convert from base unit to the best display unit."""
    if group_name not in PREFERRED_UNITS:
        return base_quantity, "pcs"
    for unit, threshold in PREFERRED_UNITS[group_name]:
        if base_quantity >= threshold:
            factor = UNIT_GROUPS[group_name][unit]
            return base_quantity / factor, unit
    # Fallback to smallest unit
    smallest_unit = PREFERRED_UNITS[group_name][-1][0]
    factor = UNIT_GROUPS[group_name][smallest_unit]
    return base_quantity / factor, smallest_unit


def parse_quantity_string(qty_str: str) -> Tuple[Optional[float], str]:
    """
    Parse a legacy quantity string like '500 g' into (value, unit).
    Returns (None, raw_string) if parsing fails.
    """
    if not qty_str or not qty_str.strip():
        return None, "pcs"

    parts = qty_str.strip().split()
    if not parts:
        return None, "pcs"

    try:
        value = float(parts[0])
        unit = " ".join(parts[1:]) if len(parts) > 1 else "pcs"
        return value, normalize_unit(unit)
    except (ValueError, IndexError):
        return None, "pcs"


def days_until(expiry_date: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    """Whole calendar days from today (UTC) until the expiry date.

    Compares dates rather than timestamps so an item expiring at 00:00 tomorrow
    is "tomorrow" all day today, independent of the current time of day.
    """
    if expiry_date is None:
        return None
    today = (now or datetime.utcnow()).date()
    return (expiry_date.date() - today).days


def compute_expiry_status(expiry_date: Optional[datetime]) -> str:
    """Compute expiry status from an actual date."""
    days_left = days_until(expiry_date)
    if days_left is None:
        return "unknown"
    if days_left < 0:
        return "expired"
    if days_left <= 3:
        return "expiring_soon"
    if days_left <= 7:
        return "use_soon"
    return "fresh"


def compute_expiry_display(expiry_date: Optional[datetime]) -> str:
    """Compute display text for an expiry date."""
    days_left = days_until(expiry_date)
    if days_left is None:
        return "No expiry set"
    if days_left < -1:
        return f"Expired {abs(days_left)} days ago"
    if days_left == -1:
        return "Expired yesterday"
    if days_left == 0:
        return "Expires today"
    if days_left == 1:
        return "Expires tomorrow"
    return f"In {days_left} days"


def parse_relative_expiry(expiry_str: str, reference_date: Optional[datetime] = None) -> Optional[datetime]:
    """
    Try to parse a relative expiry string like 'In 5 days' to an actual date.
    Uses reference_date as the baseline (defaults to now).
    Returns None if parsing fails.
    """
    if not expiry_str or not expiry_str.strip():
        return None

    cleaned = expiry_str.strip().lower()
    ref = reference_date or datetime.utcnow()

    # Pattern: "in X days"
    import re
    match = re.match(r"in\s+(\d+)\s+days?", cleaned)
    if match:
        days = int(match.group(1))
        return ref + timedelta(days=days)

    # Pattern: "in X weeks"
    match = re.match(r"in\s+(\d+)\s+weeks?", cleaned)
    if match:
        weeks = int(match.group(1))
        return ref + timedelta(days=weeks * 7)

    # Pattern: "X days"
    match = re.match(r"(\d+)\s+days?", cleaned)
    if match:
        days = int(match.group(1))
        return ref + timedelta(days=days)

    # Pattern: "X weeks"
    match = re.match(r"(\d+)\s+weeks?", cleaned)
    if match:
        weeks = int(match.group(1))
        return ref + timedelta(days=weeks * 7)

    # Pattern: "expires today"
    if "today" in cleaned:
        return ref

    # Pattern: "tomorrow"
    if "tomorrow" in cleaned:
        return ref + timedelta(days=1)

    return None


# ── Inventory Service ────────────────────────────────────────────────────

# Legacy owner of data created before authentication existed. No API route
# reads or writes it any more; scripts/claim_legacy_data.py can reassign such
# records to a real account.
DEFAULT_USER_ID = "default"


class InventoryService:
    """Shared inventory CRUD service backed by MongoDB."""

    COLLECTION = "pantry_items"
    IDEMPOTENCY_COLLECTION = "idempotency_keys"

    @classmethod
    def _get_collection(cls, db):
        return db[cls.COLLECTION]

    @classmethod
    def _get_idempotency_collection(cls, db):
        return db[cls.IDEMPOTENCY_COLLECTION]

    @classmethod
    def ensure_indexes(cls, db):
        """Create required indexes. Safe to call repeatedly."""
        coll = cls._get_collection(db)
        coll.create_index(
            [("user_id", 1), ("ingredient_id", 1)],
            unique=True,
            partialFilterExpression={"ingredient_id": {"$exists": True}},
        )
        idemp_coll = cls._get_idempotency_collection(db)
        idemp_coll.create_index("key", unique=True)
        # Allow reuse of the same collection for receipt confirmations.
        idemp_coll.create_index("created_at", expireAfterSeconds=3600)

    @classmethod
    def _check_idempotency(cls, db, key: Optional[str], user_id: str = "") -> bool:
        """
        Atomically claim an idempotency key (scoped to the user).
        Returns True if the key was already used (duplicate request).
        """
        if not key:
            return False
        coll = cls._get_idempotency_collection(db)
        try:
            coll.insert_one({"key": f"{user_id}:{key}", "user_id": user_id, "created_at": datetime.utcnow()})
            return False  # New key, not a duplicate
        except DuplicateKeyError:
            return True  # Key already exists, duplicate request

    @classmethod
    def add_stock(
        cls,
        db,
        user_id: str,
        ingredient_id: str,
        quantity: float,
        unit: str,
        expiry_date: Optional[datetime] = None,
        source: str = "manual",
        idempotency_key: Optional[str] = None,
        storage_method: Optional[str] = None,
        storage_tip: Optional[str] = None,
        ai_predicted: bool = False,
    ) -> Dict[str, Any]:
        """
        Add stock to a user's inventory for a canonical ingredient.

        Creates the inventory document if it doesn't exist.
        Appends a new batch if the document already exists.
        Merges with existing batch if units are compatible and expiry matches.
        """
        # Validate ingredient (or fallback to synthetic catalog entry for custom/receipt items)
        catalog_entry = get_catalog_entry(ingredient_id)
        if not catalog_entry:
            catalog_entry = {
                "id": ingredient_id,
                "display_name": ingredient_id.replace("_", " ").title(),
                "category": "Pantry Staples",
                "emoji": "📦",
                "default_unit": normalize_unit(unit),
                "image_asset": "",
            }

        # Check idempotency
        if cls._check_idempotency(db, idempotency_key, user_id):
            # Already processed, return current state
            return cls.get_ingredient_inventory(db, user_id, ingredient_id)

        normalized = normalize_unit(unit)
        now = datetime.utcnow()

        batch = {
            "batch_id": str(uuid.uuid4()),
            "quantity": quantity,
            "unit": normalized,
            "expiry_date": expiry_date,
            "storage_method": storage_method or ("refrigerator" if (expiry_date and (expiry_date - now).days <= 10) else "pantry"),
            "storage_tip": storage_tip or "",
            "ai_predicted": ai_predicted,
            "source": source,
            "added_at": now,
        }

        coll = cls._get_collection(db)

        # Atomic upsert: create doc if needed, push batch
        result = coll.update_one(
            {"user_id": user_id, "ingredient_id": ingredient_id},
            {
                "$push": {"batches": batch},
                "$set": {
                    "updated_at": now,
                    "storage_method": batch["storage_method"],
                    "storage_tip": batch["storage_tip"],
                },
                "$setOnInsert": {
                    "user_id": user_id,
                    "ingredient_id": ingredient_id,
                    "name": catalog_entry.get("display_name", ingredient_id.replace("_", " ").title()),
                    "category": catalog_entry.get("category", "Produce"),
                    "emoji": catalog_entry.get("emoji", "📦"),
                    "created_at": now,
                },
            },
            upsert=True,
        )

        return cls.get_ingredient_inventory(db, user_id, ingredient_id)

    @classmethod
    def add_stock_batch(
        cls,
        db,
        user_id: str,
        items: List[Dict[str, Any]],
        source: str = "scanner",
        idempotency_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Add multiple items at once. Each item should have:
        - ingredient_id: str
        - quantity: float
        - unit: str
        - expiry_date: Optional[datetime]
        - storage_method: Optional[str]
        - storage_tip: Optional[str]
        - ai_predicted: Optional[bool]
        """
        if cls._check_idempotency(db, idempotency_key, user_id):
            return cls.get_user_inventory(db, user_id)

        results = []
        for item in items:
            ingredient_id = item.get("ingredient_id")
            if not ingredient_id:
                # Try to normalize the name
                name = item.get("name", "")
                ingredient_id = normalize_ingredient_name(name)
                if not ingredient_id:
                    continue  # Skip unknown ingredients

            try:
                result = cls.add_stock(
                    db=db,
                    user_id=user_id,
                    ingredient_id=ingredient_id,
                    quantity=float(item.get("quantity", 1)),
                    unit=str(item.get("unit", "pcs")),
                    expiry_date=item.get("expiry_date"),
                    source=source,
                    storage_method=item.get("storage_method"),
                    storage_tip=item.get("storage_tip"),
                    ai_predicted=bool(item.get("ai_predicted", False)),
                )
                results.append(result)
            except (ValueError, TypeError) as e:
                print(f"Skipping item {item}: {e}")

        return cls.get_user_inventory(db, user_id)

    @classmethod
    def remove_stock(
        cls,
        db,
        user_id: str,
        ingredient_id: str,
        quantity: float,
        unit: str,
    ) -> Dict[str, Any]:
        """
        Remove stock from inventory (e.g., recipe consumption).
        Removes from oldest batch first (FIFO by expiry_date).
        """
        normalized = normalize_unit(unit)
        coll = cls._get_collection(db)
        doc = coll.find_one({"user_id": user_id, "ingredient_id": ingredient_id})

        if not doc or not doc.get("batches"):
            raise ValueError(f"No stock found for {ingredient_id}")

        # Sort batches by expiry (earliest first, None last)
        batches = sorted(
            doc["batches"],
            key=lambda b: b.get("expiry_date") or datetime(9999, 12, 31),
        )

        if quantity <= 0:
            raise ValueError("Quantity to remove must be positive")
        remaining_base, req_group = convert_to_base(quantity, normalized)
        updated_batches = []

        for batch in batches:
            batch_unit = normalize_unit(batch.get("unit", "pcs"))
            if remaining_base <= 0 or not units_compatible(batch_unit, normalized):
                updated_batches.append(batch)
                continue
            batch_base, _ = convert_to_base(float(batch.get("quantity", 0)), batch_unit)
            if batch_base <= remaining_base + 1e-9:
                remaining_base -= batch_base  # batch fully consumed
            else:
                factor = UNIT_GROUPS[req_group][batch_unit] if batch_unit in UNIT_GROUPS.get(req_group, {}) else 1.0
                batch["quantity"] = round((batch_base - remaining_base) / factor, 4)
                remaining_base = 0
                updated_batches.append(batch)

        now = datetime.utcnow()
        if updated_batches:
            coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"batches": updated_batches, "updated_at": now}},
            )
        else:
            coll.delete_one({"_id": doc["_id"]})

        return cls.get_ingredient_inventory(db, user_id, ingredient_id)

    @classmethod
    def set_stock(
        cls,
        db,
        user_id: str,
        ingredient_id: str,
        quantity: float,
        unit: str,
        expiry_date: Optional[datetime] = None,
        storage_method: Optional[str] = None,
        storage_tip: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Replace an item's batches with a single batch (manual edit)."""
        coll = cls._get_collection(db)
        doc = coll.find_one({"user_id": user_id, "ingredient_id": ingredient_id})
        if not doc:
            return None
        if quantity <= 0:
            coll.delete_one({"_id": doc["_id"]})
            return cls.get_ingredient_inventory(db, user_id, ingredient_id)
        prev = (doc.get("batches") or [{}])[0]
        now = datetime.utcnow()
        batch = {
            "batch_id": str(uuid.uuid4()),
            "quantity": float(quantity),
            "unit": normalize_unit(unit),
            "expiry_date": expiry_date,
            "storage_method": storage_method or prev.get("storage_method") or doc.get("storage_method", "pantry"),
            "storage_tip": storage_tip if storage_tip is not None else prev.get("storage_tip", ""),
            "ai_predicted": False,
            "source": "manual_edit",
            "added_at": prev.get("added_at") or now,
        }
        coll.update_one(
            {"_id": doc["_id"]},
            {"$set": {"batches": [batch], "updated_at": now,
                      "storage_method": batch["storage_method"], "storage_tip": batch["storage_tip"]}},
        )
        return cls.get_ingredient_inventory(db, user_id, ingredient_id)

    @classmethod
    def delete_inventory(cls, db, user_id: str, ingredient_id: str) -> bool:
        """Delete all stock for a specific ingredient."""
        coll = cls._get_collection(db)
        result = coll.delete_one({"user_id": user_id, "ingredient_id": ingredient_id})
        return result.deleted_count > 0

    @classmethod
    def get_ingredient_inventory(
        cls, db, user_id: str, ingredient_id: str
    ) -> Dict[str, Any]:
        """Get inventory for a single ingredient, merged with catalog."""
        catalog_entry = get_catalog_entry(ingredient_id) or {}
        coll = cls._get_collection(db)
        doc = coll.find_one({"user_id": user_id, "ingredient_id": ingredient_id})

        return cls._merge_catalog_inventory(catalog_entry, doc)

    @classmethod
    def get_user_inventory(cls, db, user_id: str) -> List[Dict[str, Any]]:
        """Get all stocked items for a user."""
        coll = cls._get_collection(db)
        docs = list(coll.find({"user_id": user_id, "ingredient_id": {"$exists": True}}))
        catalog = get_catalog()

        results = []
        for doc in docs:
            ing_id = doc.get("ingredient_id", "")
            catalog_entry = catalog.get(ing_id, {})
            results.append(cls._merge_catalog_inventory(catalog_entry, doc))

        return results

    @classmethod
    def get_full_pantry_view(cls, db, user_id: str) -> List[Dict[str, Any]]:
        """
        Get ALL 22 catalog items merged with user inventory.
        Items without stock appear with in_stock=False.
        """
        catalog = get_catalog()
        coll = cls._get_collection(db)
        docs = list(coll.find({"user_id": user_id, "ingredient_id": {"$exists": True}}))

        # Index inventory by ingredient_id
        inventory_map = {}
        for doc in docs:
            ing_id = doc.get("ingredient_id", "")
            if ing_id:
                inventory_map[ing_id] = doc

        results = []
        for ingredient_id, entry in sorted(catalog.items(), key=lambda x: x[1]["class_index"]):
            doc = inventory_map.get(ingredient_id)
            results.append(cls._merge_catalog_inventory(entry, doc))

        return results

    @classmethod
    def _merge_catalog_inventory(
        cls, catalog_entry: Dict[str, Any], inventory_doc: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Merge a catalog entry with an inventory document for API response."""
        ingredient_id = (
            catalog_entry.get("id")
            or (inventory_doc.get("ingredient_id") if inventory_doc else None)
            or "unknown"
        )
        display_name = (
            catalog_entry.get("display_name")
            or (inventory_doc.get("name") if inventory_doc else None)
            or (inventory_doc.get("display_name") if inventory_doc else None)
            or ingredient_id.replace("_", " ").title()
        )
        category = (
            catalog_entry.get("category")
            or (inventory_doc.get("category") if inventory_doc else None)
            or "Produce"
        )
        emoji = (
            catalog_entry.get("emoji")
            or (inventory_doc.get("emoji") if inventory_doc else None)
            or "📦"
        )
        default_unit = (
            catalog_entry.get("default_unit")
            or (inventory_doc.get("unit") if inventory_doc else None)
            or "pcs"
        )
        image_asset = catalog_entry.get("image_asset", "")

        if inventory_doc and inventory_doc.get("batches"):
            batches = inventory_doc["batches"]
            in_stock = True

            # Aggregate quantities by unit group
            quantities_by_group: Dict[str, Tuple[float, str]] = {}
            for batch in batches:
                batch_unit = normalize_unit(batch.get("unit", "pcs"))
                batch_qty = batch.get("quantity", 0)
                group = get_unit_group(batch_unit) or "unknown"

                base_qty, _ = convert_to_base(batch_qty, batch_unit)
                if group in quantities_by_group:
                    existing_base, _ = quantities_by_group[group]
                    quantities_by_group[group] = (existing_base + base_qty, group)
                else:
                    quantities_by_group[group] = (base_qty, group)

            # Build display quantities
            display_parts = []
            total_quantity = 0
            primary_unit = default_unit

            for group_name, (base_qty, _) in quantities_by_group.items():
                display_qty, display_unit = convert_from_base(base_qty, group_name)
                if display_qty == int(display_qty):
                    display_parts.append(f"{int(display_qty)} {display_unit}")
                else:
                    display_parts.append(f"{display_qty:.1f} {display_unit}")
                total_quantity = display_qty
                primary_unit = display_unit

            display_quantity = " + ".join(display_parts) if display_parts else "0 pcs"

            # Earliest expiry across all batches
            expiry_dates = [b["expiry_date"] for b in batches if b.get("expiry_date")]
            earliest_expiry = min(expiry_dates) if expiry_dates else None
            expiry_display = compute_expiry_display(earliest_expiry)
            expiry_status = compute_expiry_status(earliest_expiry)

            # Storage metadata from earliest expiring batch or latest batch
            active_batch = next((b for b in batches if b.get("expiry_date")), batches[0] if batches else {})
            storage_method = active_batch.get("storage_method") or inventory_doc.get("storage_method", "pantry")
            storage_tip = active_batch.get("storage_tip") or inventory_doc.get("storage_tip", "")
            ai_predicted = any(b.get("ai_predicted") for b in batches)

            # Format batches for response
            response_batches = []
            for b in batches:
                exp_date = b.get("expiry_date")
                response_batches.append({
                    "batch_id": b.get("batch_id", ""),
                    "quantity": b.get("quantity", 0),
                    "unit": b.get("unit", "pcs"),
                    "expiry_date": exp_date.isoformat() if exp_date else None,
                    "expiry_display": compute_expiry_display(exp_date),
                    "expiry_status": compute_expiry_status(exp_date),
                    "storage_method": b.get("storage_method", "pantry"),
                    "storage_tip": b.get("storage_tip", ""),
                    "ai_predicted": b.get("ai_predicted", False),
                    "source": b.get("source", "unknown"),
                    "added_at": b.get("added_at", "").isoformat() if isinstance(b.get("added_at"), datetime) else None,
                })
        else:
            in_stock = False
            total_quantity = 0
            primary_unit = default_unit
            display_quantity = "Not in pantry"
            earliest_expiry = None
            expiry_display = "Not in pantry"
            expiry_status = "empty"
            storage_method = "pantry"
            storage_tip = ""
            ai_predicted = False
            response_batches = []

        return {
            "ingredient_id": ingredient_id,
            "display_name": display_name,
            "category": category,
            "emoji": emoji,
            "image_asset": image_asset,
            "in_stock": in_stock,
            "total_quantity": total_quantity,
            "unit": primary_unit,
            "display_quantity": display_quantity,
            "batches": response_batches,
            "earliest_expiry": earliest_expiry.isoformat() if earliest_expiry else None,
            "expiry_display": expiry_display,
            "expiry_status": expiry_status,
            "storage_method": storage_method,
            "storage_tip": storage_tip,
            "ai_predicted": ai_predicted,
        }
