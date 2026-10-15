"""Meal planner routes — scoped to the authenticated user."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..database.connection import get_database
from ..middleware.auth_middleware import get_current_user
from ..services.meal_planner_service import MealPlannerService

router = APIRouter()


class GenerateMealPlanRequest(BaseModel):
    days: int = Field(7, ge=1, le=7)
    dietary_preferences: Optional[List[str]] = Field(None, max_length=10)
    calorie_target: Optional[str] = Field(None, max_length=40)


class UpdateMealRequest(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    meal_type: str = Field(..., pattern=r"^(breakfast|lunch|dinner)$")
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    prep_time: Optional[str] = Field(None, max_length=40)
    calories: Optional[str] = Field(None, max_length=40)


@router.get("/plan")
def get_meal_plan(user_id: str = Depends(get_current_user), database=Depends(get_database)):
    return MealPlannerService.get_meal_plan(database, user_id=user_id)


@router.post("/generate")
def generate_meal_plan(request: GenerateMealPlanRequest, user_id: str = Depends(get_current_user),
                       database=Depends(get_database)):
    result = MealPlannerService.generate_meal_plan(
        database=database, user_id=user_id, days_count=request.days,
        dietary_preferences=request.dietary_preferences, calorie_target=request.calorie_target,
    )
    if not result.get("success"):
        code = 400 if result.get("reason") == "empty_pantry" else 502
        raise HTTPException(status_code=code, detail=result.get("message", "Could not generate a meal plan."))
    return result


@router.put("/update")
def update_meal(request: UpdateMealRequest, user_id: str = Depends(get_current_user),
                database=Depends(get_database)):
    meal_data = request.model_dump(exclude_none=True, exclude={"date", "meal_type"})
    result = MealPlannerService.update_meal(database=database, user_id=user_id, date_str=request.date,
                                            meal_type=request.meal_type, meal_data=meal_data)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Update failed"))
    return result


@router.delete("/plan")
def reset_meal_plan(user_id: str = Depends(get_current_user), database=Depends(get_database)):
    database["meal_plans"].delete_many({"user_id": user_id})
    return MealPlannerService.get_meal_plan(database, user_id=user_id)
