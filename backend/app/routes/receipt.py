"""
Receipt scanning.

POST /api/receipt/process  extract items from a photo (nothing is saved)
POST /api/receipt/confirm  save the items the user reviewed + record the expense
                           (idempotent: retries never duplicate data)
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..database.connection import get_database
from ..middleware.auth_middleware import get_current_user
from ..services.expense_service import ExpenseService
from ..services.gemini_client import GeminiError, GeminiNotConfigured
from ..services.gemini_service import GeminiService
from ..services.inventory_service import InventoryService
from ..utils.uploads import read_image_upload
from .pantry import PantryAddItem, _resolve_items, build_full_view

router = APIRouter()


class ReceiptExpense(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0, le=10_000_000)
    category: str = Field("Groceries", max_length=40)
    date: Optional[str] = Field(None, max_length=10)
    notes: Optional[str] = Field(None, max_length=500)


class ReceiptConfirmRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=100)
    items: List[PantryAddItem] = Field(default_factory=list, max_length=100)
    expense: Optional[ReceiptExpense] = None


@router.post("/process")
async def process_receipt(file: UploadFile = File(...), user_id: str = Depends(get_current_user)):
    data, mime = await read_image_upload(file)
    try:
        # Blocking HTTP call: run in the threadpool, not on the event loop.
        result = await run_in_threadpool(GeminiService.process_receipt_image, data, mime)
    except GeminiNotConfigured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Receipt scanning is not configured on the server.")
    except GeminiError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    if not result["is_receipt"]:
        raise HTTPException(status_code=422, detail="This photo doesn't look like a receipt. Please try again.")
    if not result["items"]:
        raise HTTPException(status_code=422,
                            detail="No items could be read from this receipt. Try a sharper, well-lit photo.")
    return result


@router.post("/confirm")
def confirm_receipt(payload: ReceiptConfirmRequest, user_id: str = Depends(get_current_user),
                    database=Depends(get_database)):
    if not payload.items and not payload.expense:
        raise HTTPException(status_code=400, detail="Nothing to save.")
    if payload.expense and payload.expense.date:
        try:
            datetime.strptime(payload.expense.date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Expense date must be YYYY-MM-DD.")

    if InventoryService._check_idempotency(database, f"receipt:{payload.idempotency_key}", user_id):
        return {"success": True, "duplicate": True, "pantry": build_full_view(database, user_id), "expense": None}

    added = 0
    if payload.items:
        resolved = _resolve_items(payload.items)
        InventoryService.add_stock_batch(db=database, user_id=user_id, items=resolved, source="receipt")
        added = len(resolved)

    expense = None
    if payload.expense:
        e = payload.expense
        expense = ExpenseService.add_expense(
            database, user_id=user_id, title=e.title, amount=e.amount, category=e.category,
            date_str=e.date, notes=e.notes, source="receipt",
        )["expense"]

    return {"success": True, "duplicate": False, "items_added": added,
            "pantry": build_full_view(database, user_id), "expense": expense}
