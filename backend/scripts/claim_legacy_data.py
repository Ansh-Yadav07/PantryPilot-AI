#!/usr/bin/env python3
"""
Assign records created before authentication existed (owner "default") to a
real account. Nothing is deleted. Dry run unless --apply is given.

    python scripts/claim_legacy_data.py you@example.com           # preview
    python scripts/claim_legacy_data.py you@example.com --apply   # reassign

Reads MONGODB_URI / DATABASE_NAME from the environment or backend/.env.
If the account already has an item for the same vegetable, the legacy
batches are merged into it rather than creating a duplicate.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.connection import Database  # noqa: E402
from app.services.auth_service import get_user_by_email  # noqa: E402

LEGACY = "default"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("email")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = Database.get_db()
    if db is None or not Database.ping():
        sys.exit("Cannot connect to MongoDB (check MONGODB_URI).")
    user = get_user_by_email(db, args.email)
    if not user:
        sys.exit(f"No account with email {args.email}. Register in the app first.")
    uid = str(user["_id"])

    pantry = list(db.pantry_items.find({"user_id": LEGACY}))
    print(f"Account: {user['name']} <{user['email']}> ({uid})")
    print(f"Legacy pantry items: {len(pantry)}")
    for coll in ("expenses", "shopping_items", "meal_plans"):
        print(f"Legacy {coll}: {db[coll].count_documents({'user_id': LEGACY})}")
    if not args.apply:
        print("\nDry run only. Re-run with --apply to reassign these records.")
        return

    merged = moved = 0
    for doc in pantry:
        existing = db.pantry_items.find_one({"user_id": uid, "ingredient_id": doc.get("ingredient_id")})
        if existing:
            db.pantry_items.update_one({"_id": existing["_id"]}, {"$push": {"batches": {"$each": doc.get("batches", [])}}})
            db.pantry_items.update_one({"_id": doc["_id"]}, {"$set": {"user_id": f"{LEGACY}-merged-into-{uid}"}})
            merged += 1
        else:
            db.pantry_items.update_one({"_id": doc["_id"]}, {"$set": {"user_id": uid}})
            moved += 1
    other = {c: db[c].update_many({"user_id": LEGACY}, {"$set": {"user_id": uid}}).modified_count
             for c in ("expenses", "shopping_items")}
    if db.meal_plans.count_documents({"user_id": uid}) == 0:
        other["meal_plans"] = db.meal_plans.update_many({"user_id": LEGACY}, {"$set": {"user_id": uid}}).modified_count
    print(f"Pantry: {moved} moved, {merged} merged into existing items. Other: {other}")


if __name__ == "__main__":
    main()
