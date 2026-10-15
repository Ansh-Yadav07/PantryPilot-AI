"""
AnalyticsService — kitchen metrics computed from the user's real pantry and
expenses. Waste risk uses the rule-based WastePredictionService (expiry-date
thresholds), and is labelled as such; it is not an ML model.
"""

from datetime import datetime
from typing import Any, Dict

from .expense_service import ExpenseService
from .inventory_service import InventoryService
from .waste_prediction import WastePredictionService


class AnalyticsService:
    @classmethod
    def get_analytics(cls, db, user_id: str) -> Dict[str, Any]:
        total = fresh = expiring = expired = 0
        categories: Dict[str, int] = {}
        at_risk = []

        for item in InventoryService.get_user_inventory(db, user_id):
            if not item.get("in_stock"):
                continue
            total += 1
            cat = item.get("category") or "Other"
            categories[cat] = categories.get(cat, 0) + 1
            status = item.get("expiry_status", "")
            if status == "expired":
                expired += 1
            elif status in ("expiring_soon", "use_soon"):
                expiring += 1
            else:
                fresh += 1
            if item.get("earliest_expiry"):
                risk = WastePredictionService.predict_waste_risk(
                    item["display_name"], datetime.fromisoformat(item["earliest_expiry"]), item.get("total_quantity", 0))
                if risk["riskLevel"] in ("CRITICAL", "HIGH"):
                    at_risk.append({"ingredient_id": item["ingredient_id"], "name": item["display_name"],
                                    "emoji": item.get("emoji"), "risk_level": risk["riskLevel"],
                                    "reason": risk["reason"], "expiry_display": item.get("expiry_display")})

        breakdown = sorted(
            ({"category": c, "count": n, "percentage": round(n / total * 100, 1) if total else 0.0}
             for c, n in categories.items()),
            key=lambda x: x["count"], reverse=True,
        )

        summary = ExpenseService.get_summary(db, user_id)
        this_m, last_m = summary["total_this_month"], summary["total_last_month"]
        if last_m > 0:
            diff = (this_m - last_m) / last_m * 100
            comparison = f"{'↑' if diff >= 0 else '↓'} {abs(diff):.1f}% vs last month"
        else:
            comparison = "No spending recorded last month"

        return {
            "monthly_spend_raw": this_m,
            "last_month_spend_raw": last_m,
            "spend_comparison": comparison,
            "total_pantry_items": total,
            "fresh_items_count": fresh,
            "expiring_soon_count": expiring,
            "expired_count": expired,
            "at_risk_items": at_risk,
            "waste_risk_method": "rule_based_expiry_thresholds",
            "pantry_categories": breakdown,
            "weekly_spending": summary["weekly_spending"],
            "expense_count": summary["expense_count"],
            "expense_categories": summary["category_breakdown"],
        }
