"""
AiInsightService — Generates personalized pantry and spending insights using Google Gemini AI.
Integrates user's real inventory expiry dates, ingredient stock levels, and spending history.
"""

import logging
from typing import List, Dict, Any, Tuple

from . import gemini_client
from .gemini_client import GeminiError, GeminiNotConfigured
from .inventory_service import InventoryService
from .expense_service import ExpenseService

logger = logging.getLogger("pantrypilot.insights")


class AiInsightService:
    @classmethod
    def generate_insights(
        cls,
        db,
        user_id: str,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Produce real AI insights tailored to user's real pantry items and expenses.
        """
        # 1. Fetch real pantry data
        pantry_items = []
        expiring_items = []
        low_stock_items = []

        if db is not None:
            try:
                inventory = InventoryService.get_user_inventory(db, user_id)
                for item in inventory:
                    if item.get("in_stock"):
                        name = item.get("display_name") or item.get("name") or "Item"
                        qty = item.get("display_quantity", "1 unit")
                        exp_status = item.get("expiry_status", "")
                        exp_display = item.get("expiry_display", "")

                        pantry_items.append(f"{name} ({qty}) - {exp_display}")

                        if exp_status in ("expired", "expiring_soon", "use_soon"):
                            expiring_items.append(f"{name} ({exp_display})")
            except Exception:
                logger.exception("Error loading inventory for AI insights")

        # 2. Fetch real expense data
        expense_summary = {}
        if db is not None:
            try:
                expense_summary = ExpenseService.get_summary(db, user_id)
            except Exception:
                logger.exception("Error loading expenses for AI insights")

        total_spent = expense_summary.get("total_this_month", 0.0)
        recent_expenses = expense_summary.get("expenses", [])[:5]
        top_cats = [c["category"] for c in expense_summary.get("category_breakdown", [])[:3]]

        # 3. Call Gemini if API key configured
        if gemini_client.is_configured() and pantry_items:
            try:
                pantry_str = "\n".join(pantry_items[:15]) if pantry_items else "No tracked pantry items yet."
                expiring_str = ", ".join(expiring_items[:5]) if expiring_items else "None"
                recent_exp_str = ", ".join([f"{e.get('title')}: ₹{e.get('amount')}" for e in recent_expenses]) if recent_expenses else "None yet"

                prompt = f"""You are PantryPilot AI's chief kitchen & finance strategist.
Analyze the user's REAL pantry inventory and grocery expenses:

USER'S CURRENT PANTRY:
{pantry_str}

ITEMS EXPIRING SOON:
{expiring_str}

EXPENSES THIS MONTH:
Total Spent: ₹{total_spent}
Top Categories: {', '.join(top_cats) if top_cats else 'General'}
Recent Purchases: {recent_exp_str}

TASK:
Generate exactly 4 concise, high-value, personalized insights based SPECIFICALLY on their real items and spending above.
Include practical suggestions:
1. One Expiration / Waste Alert (mention their specific expiring items if any, or general fresh maintenance).
2. One Smart Shopping / Replenishment Habit insight (based on low stock items or recent purchases).
3. One Dietary or Recipe Suggestion (incorporating their actual pantry items).
4. One Budget or Waste Savings Tip (personalized to their expenditure).

Return ONLY a valid JSON list of 4 objects matching this schema:
[
  {{
    "title": "Short punchy title (3-5 words)",
    "description": "Clear, actionable insight (1-2 sentences referencing their real pantry or spending).",
    "emoji": "Single emoji icon",
    "category": "Alert" | "Habit" | "Dietary" | "Savings" | "Tip",
    "color_type": "warning" | "primary" | "secondary" | "accent"
  }}
]
Do not wrap in markdown or backticks. Return only valid JSON array.
"""
                parsed = gemini_client.generate_json([prompt], timeout=30.0, temperature=0.6)
                if isinstance(parsed, list) and len(parsed) >= 3:
                    return [p for p in parsed if isinstance(p, dict)], "gemini"
            except (GeminiError, GeminiNotConfigured) as e:
                logger.info("AI insights falling back to rule-based summary: %s", e)

        # 4. Dynamic Fallback derived from REAL user data (not fake static data)
        return cls._build_dynamic_insights(expiring_items, pantry_items, total_spent, top_cats), "rules"

    @classmethod
    def _build_dynamic_insights(
        cls,
        expiring_items: List[str],
        pantry_items: List[str],
        total_spent: float,
        top_cats: List[str],
    ) -> List[Dict[str, Any]]:
        insights = []

        # 1. Expiry insight
        if expiring_items:
            items_str = ", ".join(expiring_items[:3])
            insights.append({
                "title": "Immediate Consumption Alert",
                "description": f"You have items expiring soon: {items_str}. Prioritize these in your next meal to eliminate waste.",
                "emoji": "⚠️",
                "category": "Alert",
                "color_type": "warning",
            })
        else:
            insights.append({
                "title": "Fresh Pantry Status",
                "description": f"All {len(pantry_items)} pantry items are within safe shelf life. Keep ingredients sealed properly to maximize freshness.",
                "emoji": "✅",
                "category": "Alert",
                "color_type": "primary",
            })

        # 2. Shopping insight
        if total_spent > 0:
            cat_str = f" in {top_cats[0]}" if top_cats else ""
            insights.append({
                "title": "Spending Distribution",
                "description": f"You've recorded ₹{total_spent:,.0f} in food expenses{cat_str}. Plan meals ahead to reduce unneeded grocery runs.",
                "emoji": "📊",
                "category": "Savings",
                "color_type": "secondary",
            })
        else:
            insights.append({
                "title": "Expense Tracking",
                "description": "Log your recent grocery bills in the Expenses tab to unlock personalized cost-saving projections.",
                "emoji": "💡",
                "category": "Habit",
                "color_type": "secondary",
            })

        # 3. Dietary / Recipe insight
        if pantry_items:
            first_few = [p.split(" (")[0] for p in pantry_items[:3]]
            insights.append({
                "title": "Recipe Recommendation",
                "description": f"You have {', '.join(first_few)} available. Try combining them into a stir-fry, skillet, or one-pot bake.",
                "emoji": "🥗",
                "category": "Dietary",
                "color_type": "primary",
            })
        else:
            insights.append({
                "title": "Inventory Kickstart",
                "description": "Scan receipts or ingredients using the Pantry scanner to keep automated tabs on your food supply.",
                "emoji": "🥑",
                "category": "Dietary",
                "color_type": "primary",
            })

        # 4. Waste reduction tip
        insights.append({
            "title": "Smart Food Preservation",
            "description": "Freezing herbs in olive oil and keeping root vegetables in cool, dark spots extends shelf life by up to 3 weeks.",
            "emoji": "🌱",
            "category": "Tip",
            "color_type": "accent",
        })

        return insights
