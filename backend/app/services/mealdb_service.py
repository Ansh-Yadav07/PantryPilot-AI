# pyrefly: ignore [missing-import]
import json
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger("pantrypilot.mealdb")

class MealDBService:
    BASE_URL = "https://www.themealdb.com/api/json/v1/1"

    @classmethod
    def _fetch_json(cls, url: str) -> Optional[Dict[str, Any]]:
        try:
            req = urllib.request.Request(
                url, 
                headers={"User-Agent": "PantryAI/1.0"}
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = response.read().decode('utf-8')
                    return json.loads(data)
        except Exception as e:
            logger.info("MealDB request failed: %s", type(e).__name__)
        return None

    @classmethod
    def search_meal(cls, query: str) -> Optional[Dict[str, Any]]:
        if not query:
            return None
            
        encoded_query = urllib.parse.quote(query.strip())
        url = f"{cls.BASE_URL}/search.php?s={encoded_query}"
        result = cls._fetch_json(url)
        
        if result and result.get("meals"):
            meal = result["meals"][0]
            return {
                "id": meal.get("idMeal"),
                "name": meal.get("strMeal"),
                "category": meal.get("strCategory"),
                "area": meal.get("strArea"),
                "instructions": meal.get("strInstructions"),
                "image_url": meal.get("strMealThumb"),
                "video_url": meal.get("strYoutube"),
                "source_url": meal.get("strSource"),
                "tags": meal.get("strTags")
            }
        return None

    @classmethod
    def filter_by_ingredient(cls, ingredient: str) -> List[Dict[str, Any]]:
        if not ingredient:
            return []
            
        encoded_ing = urllib.parse.quote(ingredient.strip().lower())
        url = f"{cls.BASE_URL}/filter.php?i={encoded_ing}"
        result = cls._fetch_json(url)
        
        meals = []
        if result and result.get("meals"):
            for m in result["meals"][:5]:
                meals.append({
                    "id": m.get("idMeal"),
                    "name": m.get("strMeal"),
                    "image_url": m.get("strMealThumb")
                })
        return meals

    @classmethod
    def exact_match(cls, recipe_name: str) -> Optional[Dict[str, Any]]:
        """Return MealDB metadata only when the dish name matches exactly."""
        meal = cls.search_meal(recipe_name)
        if meal and (meal.get("name") or "").strip().lower() == recipe_name.strip().lower():
            return meal
        return None

    @classmethod
    def enrich_recipe(cls, recipe_name: str, primary_ingredient: str = "") -> Dict[str, Any]:
        """
        Tries to match a recipe name on TheMealDB to fetch HD thumbnail, YouTube link, and cuisine category.
        Falls back to primary ingredient search if dish name search returns nothing.
        """
        # 1. Try search by full or partial dish name
        meal = cls.search_meal(recipe_name)
        
        # 2. If no direct match, try individual words in recipe name
        if not meal and recipe_name:
            words = recipe_name.split()
            for word in words:
                if len(word) > 3 and word.lower() not in ["with", "and", "toast", "salad", "soup", "bowl", "stir"]:
                    meal = cls.search_meal(word)
                    if meal:
                        break

        # 3. If still no match, try filtering by primary ingredient
        if not meal and primary_ingredient:
            filtered = cls.filter_by_ingredient(primary_ingredient)
            if filtered and len(filtered) > 0:
                meal = cls.search_meal(filtered[0]["name"])

        if meal:
            return {
                "image_url": meal.get("image_url"),
                "video_url": meal.get("video_url"),
                "category": meal.get("category", "General"),
                "area": meal.get("area", "International"),
                "instructions": meal.get("instructions"),
            }

        # Fallback default image placeholders based on query keywords
        return {
            "image_url": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80",
            "video_url": None,
            "category": "Quick Meal",
            "area": "Global",
            "instructions": None
        }

