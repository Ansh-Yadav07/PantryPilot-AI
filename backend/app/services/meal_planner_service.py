"""
MealPlannerService — AI-powered meal planning using Gemini API, MongoDB Atlas, and TheMealDB.
"""

import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from . import gemini_client
from .gemini_client import GeminiError, GeminiNotConfigured
from .mealdb_service import MealDBService
from .inventory_service import InventoryService

logger = logging.getLogger("pantrypilot.meals")


class MealPlannerService:
    @classmethod
    def get_meal_plan(cls, database, user_id: str) -> Dict[str, Any]:
        """Fetch the current saved meal plan for the user, or return default 7-day schedule."""
        today = datetime.now()
        date_keys = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

        if database is not None:
            doc = database["meal_plans"].find_one({"user_id": user_id})
            if doc and "days" in doc and len(doc["days"]) > 0:
                doc["_id"] = str(doc["_id"])
                return {
                    "success": True,
                    "user_id": user_id,
                    "updated_at": doc.get("updated_at"),
                    "generated_with_ai": doc.get("generated_with_ai", False),
                    "days": doc["days"]
                }

        # No saved plan yet — return empty days so user sees empty pantry/schedule state
        return {
            "success": True,
            "user_id": user_id,
            "updated_at": None,
            "generated_with_ai": False,
            "days": []
        }

    @classmethod
    def generate_meal_plan(
        cls,
        database,
        user_id: str,
        days_count: int = 7,
        dietary_preferences: Optional[List[str]] = None,
        calorie_target: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Uses Google Gemini to generate a personalized 7-day meal plan based on
        the user's real pantry ingredients, prioritizing items expiring soon.
        """
        today = datetime.now()
        pantry_lines = []
        expiring_items = []
        all_ingredients = []

        if database is not None:
            try:
                inventory = InventoryService.get_user_inventory(database, user_id)
                for item in inventory:
                    if item.get("in_stock"):
                        name = item.get("display_name", "")
                        all_ingredients.append(name)
                        exp_status = item.get("expiry_status", "")
                        exp_display = item.get("expiry_display", "")
                        
                        line = f"- {name} ({item.get('display_quantity', '')})"
                        if exp_status in ("expiring_soon", "use_soon"):
                            line += f" [EXPIRING SOON: {exp_display}]"
                            expiring_items.append(name)
                        pantry_lines.append(line)

            except Exception:
                logger.exception("Error loading pantry inventory for meal planner")
        if not all_ingredients:
            return {
                "success": False,
                "user_id": user_id,
                "reason": "empty_pantry",
                "message": "Your pantry is empty. Please add ingredients to your pantry first to generate a meal plan.",
                "days": []
            }

        pantry_context = "\n".join(pantry_lines)
        
        pref_str = f"Dietary requirements: {', '.join(dietary_preferences)}." if dietary_preferences else ""
        cal_str = f"Target calories per day: {calorie_target}." if calorie_target else ""

        # Prepare dates
        date_specs = []
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for i in range(days_count):
            d = today + timedelta(days=i)
            date_specs.append({
                "date": d.strftime("%Y-%m-%d"),
                "day_name": day_names[d.weekday()],
                "day_short": d.strftime("%a"),
                "day_number": d.day,
                "is_today": (i == 0)
            })

        generated_days = []
        ai_success = False

        error_message = "AI could not generate a meal plan. Please try again."
        try:
            dates_prompt = "\n".join([f"- Day {i+1} ({ds['day_name']}, {ds['date']})" for i, ds in enumerate(date_specs)])
            prompt = f"""You are an executive chef and registered nutritionist.

The user wants a structured {days_count}-day meal plan (Breakfast, Lunch, and Dinner each day).
Today's date is {today.strftime('%Y-%m-%d')}.

User's current pantry items:
{pantry_context}

Items marked [EXPIRING SOON]: {', '.join(expiring_items) if expiring_items else 'None'}
{pref_str}
{cal_str}

CRITICAL RULES:
1. MAXIMIZE the use of the user's pantry items, especially items marked [EXPIRING SOON] in the first 2-3 days!
2. Create practical, delicious, and diverse home-cooked meals.
3. For each of the {days_count} days, provide 3 meals: breakfast, lunch, dinner.

Schedule to plan:
{dates_prompt}

Return ONLY a valid JSON array of {days_count} objects matching this exact schema:
[
  {{
"date": "YYYY-MM-DD",
"day_name": "DayName",
"breakfast": {{
  "name": "Recipe Name",
  "description": "Short appetizing description (1-2 sentences)",
  "prep_time": "15 mins",
  "calories": "350 kcal",
  "ingredients_used": ["Tomato", "Eggs"],
  "uses_expiring_items": true,
  "missing_ingredients": ["Bread"]
}},
"lunch": {{
  "name": "Recipe Name",
  "description": "Short appetizing description",
  "prep_time": "25 mins",
  "calories": "550 kcal",
  "ingredients_used": ["Cucumber", "Chicken"],
  "uses_expiring_items": false,
  "missing_ingredients": ["Olive oil"]
}},
"dinner": {{
  "name": "Recipe Name",
  "description": "Short appetizing description",
  "prep_time": "30 mins",
  "calories": "600 kcal",
  "ingredients_used": ["Carrot", "Potato", "Garlic"],
  "uses_expiring_items": true,
  "missing_ingredients": ["Cream"]
}}
  }}
]
Do not wrap in markdown or backticks. Return only valid JSON.
"""
            parsed = gemini_client.generate_json([prompt], timeout=90.0, temperature=0.7)
            if isinstance(parsed, dict):
                parsed = parsed.get("days") or []
            if isinstance(parsed, list) and len(parsed) > 0:
                generated_days = [d for d in parsed if isinstance(d, dict)]
                ai_success = True
        except GeminiNotConfigured:
            error_message = "Meal planning is not configured on the server."
        except GeminiError as e:
            error_message = str(e)

        # If Gemini didn't return, do NOT fabricate fake recipes
        if not generated_days:
            return {
                "success": False,
                "user_id": user_id,
                "reason": "ai_failed",
                "message": error_message,
                "days": []
            }

        # Ensure all days have date/day_name alignment and enrich each meal with TheMealDB metadata
        for idx, day_data in enumerate(generated_days):
            ref = date_specs[min(idx, len(date_specs) - 1)]
            day_data["date"] = ref["date"]
            day_data["day_name"] = ref["day_name"]
            day_data["day_short"] = ref["day_short"]
            day_data["day_number"] = ref["day_number"]
            day_data["is_today"] = ref["is_today"]

            for meal_type in ["breakfast", "lunch", "dinner"]:
                meal = day_data.get(meal_type, {})
                if not isinstance(meal, dict):
                    meal = {"name": str(meal)}
                meal_name = meal.get("name", "Nutritious Meal")
                
                # Assign high-quality appetizing image & YouTube recipe search link instantly
                # Generic illustration chosen by keyword; flagged so the UI can
                # show it as a placeholder rather than a photo of this dish.
                if not meal.get("image_url"):
                    meal["image_url"] = cls._get_meal_image_url(meal_name, meal_type)
                    meal["image_is_illustrative"] = True
                if not meal.get("video_url"):
                    meal["video_url"] = f"https://www.youtube.com/results?search_query={urllib.parse.quote(meal_name + ' recipe')}"
                
                meal.setdefault("prep_time", "20 mins")
                meal.setdefault("calories", "450 kcal")
                meal.setdefault("ingredients_used", [])
                meal.setdefault("missing_ingredients", [])
                meal.setdefault("uses_expiring_items", False)
                day_data[meal_type] = meal

        # Persist to MongoDB Atlas if connected
        if database is not None:
            try:
                database["meal_plans"].update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "user_id": user_id,
                            "days": generated_days,
                            "updated_at": datetime.utcnow().isoformat(),
                            "generated_with_ai": ai_success,
                        }
                    },
                    upsert=True
                )
            except Exception:
                logger.exception("Error saving meal plan")

        return {
            "success": True,
            "user_id": user_id,
            "generated_with_ai": ai_success,
            "updated_at": datetime.utcnow().isoformat(),
            "days": generated_days
        }

    @classmethod
    def update_meal(
        cls,
        database,
        user_id: str,
        date_str: str,
        meal_type: str,
        meal_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update or edit a specific meal slot in the user's plan."""
        if database is None:
            return {"success": False, "error": "Database unavailable"}

        doc = database["meal_plans"].find_one({"user_id": user_id})
        if not doc or "days" not in doc or not doc["days"]:
            return {"success": False, "error": "No meal plan found. Please generate a meal plan first."}
        days = doc["days"]

        updated = False
        meal_type = meal_type.lower()
        for day in days:
            if day.get("date") == date_str:
                current_meal = day.get(meal_type, {})
                current_meal.update(meal_data)
                
                # Check if we should re-enrich thumbnail
                if "name" in meal_data:
                    match = MealDBService.exact_match(meal_data["name"])
                    if match and match.get("image_url"):
                        current_meal["image_url"] = match["image_url"]
                        current_meal["image_is_illustrative"] = False
                    else:
                        current_meal["image_url"] = cls._get_meal_image_url(meal_data["name"], meal_type)
                        current_meal["image_is_illustrative"] = True
                    current_meal["video_url"] = (match or {}).get("video_url") or (
                        "https://www.youtube.com/results?search_query="
                        + urllib.parse.quote(meal_data["name"] + " recipe"))
                
                day[meal_type] = current_meal
                updated = True
                break

        if updated:
            database["meal_plans"].update_one(
                {"user_id": user_id},
                {"$set": {"days": days, "updated_at": datetime.utcnow().isoformat()}}
            )
            return {"success": True, "days": days}
        return {"success": False, "error": f"Date {date_str} not found in meal plan"}



    @classmethod
    def _get_meal_image_url(cls, name: str, meal_type: str) -> str:
        n = name.lower()
        if "pancake" in n or "waffle" in n:
            return "https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?w=600&auto=format&fit=crop&q=80"
        if "avocado" in n or "toast" in n:
            return "https://images.unsplash.com/photo-1525351484163-7529414344d8?w=600&auto=format&fit=crop&q=80"
        if "oat" in n or "smoothie" in n or "parfait" in n or "yogurt" in n:
            return "https://images.unsplash.com/photo-1517673132405-a56a62b18caf?w=600&auto=format&fit=crop&q=80"
        if "egg" in n or "omelette" in n or "scramble" in n:
            return "https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=600&auto=format&fit=crop&q=80"
        if "salad" in n or "cucumber" in n or "greens" in n:
            return "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=600&auto=format&fit=crop&q=80"
        if "pasta" in n or "spaghetti" in n or "noodle" in n:
            return "https://images.unsplash.com/photo-1621996346565-e3d5d6281699?w=600&auto=format&fit=crop&q=80"
        if "soup" in n or "stew" in n:
            return "https://images.unsplash.com/photo-1547592166-23ac45744acd?w=600&auto=format&fit=crop&q=80"
        if "curry" in n or "paneer" in n or "tikka" in n or "chole" in n:
            return "https://images.unsplash.com/photo-1585937421612-70a008356fbe?w=600&auto=format&fit=crop&q=80"
        if "pizza" in n or "flatbread" in n:
            return "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=600&auto=format&fit=crop&q=80"
        if "rice" in n or "biryani" in n or "bowl" in n:
            return "https://images.unsplash.com/photo-1516714435131-44d6b64dc6a2?w=600&auto=format&fit=crop&q=80"
        if "chicken" in n or "roast" in n or "meat" in n:
            return "https://images.unsplash.com/photo-1598515214211-89d3c73ae83b?w=600&auto=format&fit=crop&q=80"
        if "wrap" in n or "sandwich" in n or "burger" in n:
            return "https://images.unsplash.com/photo-1528735602780-2552fd46c7af?w=600&auto=format&fit=crop&q=80"
        
        if meal_type == "breakfast":
            return "https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=600&auto=format&fit=crop&q=80"
        elif meal_type == "lunch":
            return "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=600&auto=format&fit=crop&q=80"
        else:
            return "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=600&auto=format&fit=crop&q=80"
