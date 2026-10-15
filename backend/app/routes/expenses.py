"""Expense routes — scoped to the authenticated user."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..database.connection import get_database
from ..middleware.auth_middleware import get_current_user
from ..services.expense_service import ExpenseService

router = APIRouter()


class AddExpenseRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0, le=10_000_000)
    category: str = Field("Other", max_length=40)
    date: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("date")
    @classmethod
    def _date(cls, v: Optional[str]) -> Optional[str]:
        if v:
            datetime.strptime(v, "%Y-%m-%d")
        return v


@router.get("")
def get_expenses(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
                 user_id: str = Depends(get_current_user), database=Depends(get_database)):
    return ExpenseService.get_summary(database, user_id=user_id, month=month)


@router.post("", status_code=201)
def add_expense(req: AddExpenseRequest, user_id: str = Depends(get_current_user), database=Depends(get_database)):
    return ExpenseService.add_expense(database, user_id=user_id, title=req.title, amount=req.amount,
                                      category=req.category, date_str=req.date, notes=req.notes)


@router.delete("/{expense_id}")
def delete_expense(expense_id: str, user_id: str = Depends(get_current_user), database=Depends(get_database)):
    if not ExpenseService.delete_expense(database, expense_id=expense_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="Expense not found.")
    return {"success": True}
