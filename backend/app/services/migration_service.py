"""
Safe migration tool for PantryPilot AI pantry data.

Transforms legacy pantry_items documents (string quantities, relative
expiry, no canonical IDs) to the new schema (numeric quantities, actual
dates, canonical ingredient_id, batch support).

Supports:
- Dry-run mode (preview only)
- Backup before migration
- Canonical name normalization
- Quantity string parsing
- Relative expiry date resolution
- Duplicate grouping and merging
- Conflict reporting for manual review

Usage (CLI):
    python -m app.services.migration_service --dry-run
    python -m app.services.migration_service --apply
    python -m app.services.migration_service --backup
"""

import re
import uuid
import json
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple

from .ingredient_catalog import normalize_ingredient_name, get_catalog
from .inventory_service import (
    normalize_unit,
    parse_quantity_string,
    parse_relative_expiry,
    InventoryService,
    DEFAULT_USER_ID,
)


class MigrationService:
    """Migrates legacy pantry_items to the new schema."""

    BACKUP_COLLECTION = "pantry_items_backup"

    @classmethod
    def analyze(cls, db) -> Dict[str, Any]:
        """
        Dry-run analysis of existing data.
        Returns a report of what the migration would do.
        """
        collection = db["pantry_items"]
        all_docs = list(collection.find())

        report = {
            "total_documents": len(all_docs),
            "legacy_documents": 0,
            "new_format_documents": 0,
            "normalizable": [],
            "unknown_ingredients": [],
            "duplicate_groups": {},
            "quantity_parse_results": [],
            "expiry_parse_results": [],
            "conflicts": [],
            "actions": [],
        }

        # Separate legacy vs new format
        legacy_docs = []
        for doc in all_docs:
            if "ingredient_id" in doc and "batches" in doc:
                report["new_format_documents"] += 1
            else:
                report["legacy_documents"] += 1
                legacy_docs.append(doc)

        # Analyze legacy documents
        ingredient_groups: Dict[str, List[Dict]] = {}

        for doc in legacy_docs:
            name = doc.get("name", "Unknown")
            canonical_id = normalize_ingredient_name(name)

            # Quantity parsing
            qty_str = doc.get("quantity", "1 pcs")
            parsed_qty, parsed_unit = parse_quantity_string(qty_str)
            qty_result = {
                "original": qty_str,
                "parsed_quantity": parsed_qty,
                "parsed_unit": parsed_unit,
                "success": parsed_qty is not None,
            }
            report["quantity_parse_results"].append(qty_result)

            # Expiry parsing
            expiry_str = doc.get("expiry", "")
            created_at = doc.get("created_at")
            expiry_date = parse_relative_expiry(expiry_str, created_at)
            expiry_result = {
                "original": expiry_str,
                "reference_date": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
                "resolved_date": expiry_date.isoformat() if expiry_date else None,
                "success": expiry_date is not None,
                "ambiguous": expiry_date is None and bool(expiry_str),
            }
            report["expiry_parse_results"].append(expiry_result)

            if canonical_id:
                report["normalizable"].append({
                    "original_name": name,
                    "canonical_id": canonical_id,
                    "document_id": str(doc["_id"]),
                })

                key = f"{DEFAULT_USER_ID}:{canonical_id}"
                if key not in ingredient_groups:
                    ingredient_groups[key] = []
                ingredient_groups[key].append({
                    "doc_id": str(doc["_id"]),
                    "name": name,
                    "quantity": parsed_qty,
                    "unit": parsed_unit,
                    "expiry_date": expiry_date,
                    "expiry_original": expiry_str,
                    "created_at": created_at,
                })
            else:
                report["unknown_ingredients"].append({
                    "name": name,
                    "document_id": str(doc["_id"]),
                    "quantity": qty_str,
                })

        # Identify duplicates
        for key, items in ingredient_groups.items():
            if len(items) > 1:
                report["duplicate_groups"][key] = items
                report["conflicts"].append({
                    "ingredient": key.split(":")[-1],
                    "count": len(items),
                    "names": [i["name"] for i in items],
                    "quantities": [(i["quantity"], i["unit"]) for i in items],
                })

        # Determine actions
        for key, items in ingredient_groups.items():
            user_id, ingredient_id = key.split(":", 1)
            batches = []
            for item in items:
                if item["quantity"] is not None:
                    batches.append({
                        "quantity": item["quantity"],
                        "unit": item["unit"],
                        "expiry_date": item["expiry_date"],
                        "source": "migration",
                        "original_doc_id": item["doc_id"],
                    })

            report["actions"].append({
                "action": "merge" if len(items) > 1 else "transform",
                "ingredient_id": ingredient_id,
                "user_id": user_id,
                "source_documents": len(items),
                "resulting_batches": len(batches),
                "batches": batches,
            })

        report["total_legacy_documents"] = report["legacy_documents"]
        report["grouped_by_canonical"] = report["duplicate_groups"]
        report["unrecognized_documents"] = report["unknown_ingredients"]
        return report

    @classmethod
    def backup(cls, db) -> Dict[str, Any]:
        """
        Create a backup of all existing pantry_items documents.
        """
        source = db["pantry_items"]
        backup = db[cls.BACKUP_COLLECTION]

        all_docs = list(source.find())

        if not all_docs:
            return {"backed_up": 0, "collection": cls.BACKUP_COLLECTION}

        # Add backup metadata
        backup_time = datetime.utcnow()
        for doc in all_docs:
            doc["_backup_time"] = backup_time
            doc["_original_id"] = doc.pop("_id")

        backup.insert_many(all_docs)

        return {
            "backed_up": len(all_docs),
            "collection": cls.BACKUP_COLLECTION,
            "timestamp": backup_time.isoformat(),
        }

    @classmethod
    def apply(cls, db) -> Dict[str, Any]:
        """
        Apply the migration. Call analyze() first to review.

        Steps:
        1. Backup existing data
        2. Process legacy documents into new format
        3. Remove old legacy documents
        4. Ensure indexes
        """
        report = cls.analyze(db)

        if report["legacy_documents"] == 0:
            return {
                "status": "no_migration_needed",
                "message": "No legacy documents found",
                "new_format_documents": report["new_format_documents"],
            }

        # 1. Backup
        backup_result = cls.backup(db)

        # 2. Process each ingredient group
        collection = db["pantry_items"]
        migrated = 0
        skipped = 0
        errors = []

        # Collect all legacy doc IDs for cleanup
        legacy_doc_ids = set()

        for action in report["actions"]:
            ingredient_id = action["ingredient_id"]
            user_id = action["user_id"]

            try:
                # Collect source doc IDs
                for batch in action["batches"]:
                    from bson import ObjectId
                    orig_id = batch.get("original_doc_id")
                    if orig_id:
                        try:
                            if ObjectId.is_valid(orig_id):
                                legacy_doc_ids.add(ObjectId(orig_id))
                            else:
                                legacy_doc_ids.add(orig_id)
                        except Exception:
                            legacy_doc_ids.add(orig_id)

                # Create batches for new document
                new_batches = []
                for batch in action["batches"]:
                    new_batches.append({
                        "batch_id": str(uuid.uuid4()),
                        "quantity": batch["quantity"],
                        "unit": batch["unit"],
                        "expiry_date": batch["expiry_date"],
                        "source": "migration",
                        "added_at": datetime.utcnow(),
                    })

                if not new_batches:
                    skipped += 1
                    continue

                now = datetime.utcnow()

                # Upsert the new-format document
                collection.update_one(
                    {"user_id": user_id, "ingredient_id": ingredient_id},
                    {
                        "$push": {"batches": {"$each": new_batches}},
                        "$set": {"updated_at": now},
                        "$setOnInsert": {
                            "user_id": user_id,
                            "ingredient_id": ingredient_id,
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
                migrated += 1

            except Exception as e:
                errors.append({"ingredient_id": ingredient_id, "error": str(e)})

        # 3. Remove legacy documents (ones without ingredient_id)
        if legacy_doc_ids:
            collection.delete_many({"_id": {"$in": list(legacy_doc_ids)}})

        # 4. Ensure indexes
        InventoryService.ensure_indexes(db)

        return {
            "success": len(errors) == 0,
            "status": "completed",
            "backup": backup_result,
            "migrated_ingredients": migrated,
            "canonical_ingredients_created": migrated,
            "skipped": skipped,
            "errors": errors,
            "unknown_ingredients": report["unknown_ingredients"],
            "legacy_docs_removed": len(legacy_doc_ids),
        }

    @classmethod
    def rollback(cls, db) -> Dict[str, Any]:
        """
        Rollback migration using the backup collection.
        """
        backup_coll = db[cls.BACKUP_COLLECTION]
        pantry_coll = db["pantry_items"]

        backup_docs = list(backup_coll.find())
        if not backup_docs:
            return {"success": False, "status": "no_backup_found"}

        # Clear current pantry_items
        pantry_coll.delete_many({})

        # Restore from backup
        for doc in backup_docs:
            doc["_id"] = doc.pop("_original_id")
            doc.pop("_backup_time", None)

        pantry_coll.insert_many(backup_docs)

        return {
            "success": True,
            "status": "rolled_back",
            "restored_documents": len(backup_docs),
        }


# ── CLI Entry Point ──────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="PantryPilot AI Data Migration")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--apply", action="store_true", help="Apply migration")
    parser.add_argument("--backup", action="store_true", help="Create backup only")
    parser.add_argument("--rollback", action="store_true", help="Rollback migration")
    args = parser.parse_args()

    # Connect to DB
    from ..database.connection import Database
    Database.connect_db()
    db = Database.get_db()

    if args.dry_run:
        report = MigrationService.analyze(db)
        print(json.dumps(report, indent=2, default=str))
    elif args.backup:
        result = MigrationService.backup(db)
        print(json.dumps(result, indent=2, default=str))
    elif args.apply:
        result = MigrationService.apply(db)
        print(json.dumps(result, indent=2, default=str))
    elif args.rollback:
        result = MigrationService.rollback(db)
        print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()

    Database.close_db()


if __name__ == "__main__":
    main()
