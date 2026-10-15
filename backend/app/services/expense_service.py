"""
ExpenseService — grocery expense tracking backed by MongoDB.
All queries are scoped by user_id.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId

DEFAULT_CATEGORIES = [
    "Groceries", "Vegetables", "Fruits", "Dairy", "Bakery & Grains",
    "Meat & Seafood", "Snacks & Beverages", "Pantry Staples", "Other",
]


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in doc.items() if k not in ("_id", "datetime", "user_id")}
    out["id"] = str(doc["_id"])
    out["_id"] = out["id"]
    if isinstance(out.get("created_at"), datetime):
        out["created_at"] = out["created_at"].isoformat()
    return out


class ExpenseService:
    COLLECTION = "expenses"

    @classmethod
    def _col(cls, db):
        return db[cls.COLLECTION]

    @classmethod
    def ensure_indexes(cls, db) -> None:
        cls._col(db).create_index([("user_id", 1), ("date", -1)])

    @classmethod
    def add_expense(cls, db, user_id: str, title: str, amount: float, category: str = "Other",
                    date_str: Optional[str] = None, notes: Optional[str] = None,
                    source: str = "manual") -> Dict[str, Any]:
        if amount is None or float(amount) <= 0:
            raise ValueError("Amount must be greater than zero")
        if date_str:
            exp_date = datetime.strptime(date_str, "%Y-%m-%d")  # caller validates format
        else:
            exp_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        doc = {
            "user_id": user_id,
            "title": (title or "").strip()[:100] or "Grocery expense",
            "amount": round(float(amount), 2),
            "category": (category or "").strip()[:40] or "Other",
            "date": exp_date.strftime("%Y-%m-%d"),
            "notes": (notes or "").strip()[:500],
            "source": source,
            "created_at": datetime.utcnow(),
        }
        result = cls._col(db).insert_one(doc)
        doc["_id"] = result.inserted_id
        return {"success": True, "expense": _serialize(doc)}

    @classmethod
    def get_expenses(cls, db, user_id: str, month: Optional[str] = None, limit: int = 2000) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"user_id": user_id}
        if month:  # "YYYY-MM"
            query["date"] = {"$regex": f"^{month}-"}
        cursor = cls._col(db).find(query).sort([("date", -1), ("created_at", -1)]).limit(limit)
        return [_serialize(d) for d in cursor]

    @classmethod
    def delete_expense(cls, db, expense_id: str, user_id: str) -> bool:
        if not ObjectId.is_valid(expense_id):
            return False
        res = cls._col(db).delete_one({"_id": ObjectId(expense_id), "user_id": user_id})
        return res.deleted_count > 0

    @classmethod
    def get_summary(cls, db, user_id: str, month: Optional[str] = None) -> Dict[str, Any]:
        """Totals for this/last month, category split and the last 4 weeks."""
        all_expenses = cls.get_expenses(db, user_id)
        now = datetime.utcnow()
        this_key = now.strftime("%Y-%m")
        last = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        today = now.date()

        totals = {"this": 0.0, "last": 0.0, "all": 0.0}
        weekly = [0.0, 0.0, 0.0, 0.0]  # oldest -> newest, 7-day buckets ending today
        category_totals: Dict[str, float] = {}
        for exp in all_expenses:
            amt = float(exp.get("amount", 0.0))
            d = exp.get("date", "")
            totals["all"] += amt
            if d.startswith(this_key):
                totals["this"] += amt
                category_totals[exp.get("category", "Other")] = category_totals.get(exp.get("category", "Other"), 0.0) + amt
            elif d.startswith(last):
                totals["last"] += amt
            try:
                days_ago = (today - datetime.strptime(d, "%Y-%m-%d").date()).days
            except ValueError:
                continue
            if 0 <= days_ago < 28:
                weekly[3 - days_ago // 7] += amt

        month_total = totals["this"]
        breakdown = sorted(
            ({"category": c, "amount": round(a, 2),
              "percentage": round(a / month_total * 100, 1) if month_total else 0.0}
             for c, a in category_totals.items()),
            key=lambda x: x["amount"], reverse=True,
        )
        listed = [e for e in all_expenses if e.get("date", "").startswith(month)] if month else all_expenses[:200]
        return {
            "month": month or this_key,
            "total_this_month": round(totals["this"], 2),
            "total_last_month": round(totals["last"], 2),
            "total_all_time": round(totals["all"], 2),
            "expense_count": len(all_expenses),
            "category_breakdown": breakdown,
            "weekly_spending": [round(w, 2) for w in weekly],
            "expenses": listed,
        }
