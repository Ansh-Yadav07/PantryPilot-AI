"""
Ingredient catalog + optional server-side detection.

Vegetable detection normally runs ON THE PHONE (ONNX model bundled in the app).
The /detect endpoint is kept for local development only: it works when the
optional ML dependencies (requirements-ml.txt) and backend/models/best.pt are
present, and reports 503 otherwise (e.g. on the lean cloud deployment).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..middleware.auth_middleware import get_current_user
from ..services import detection_service
from ..services.ingredient_catalog import get_catalog_list, normalize_ingredient_name
from ..utils.uploads import read_image_upload

router = APIRouter()


class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class Detection(BaseModel):
    name: str
    display_name: str
    confidence: float
    bbox: BBox
    ingredient_id: Optional[str] = None


class DetectionResponse(BaseModel):
    success: bool
    detections: List[Detection]
    count: int


@router.post("/detect", response_model=DetectionResponse)
async def detect_ingredients(file: UploadFile = File(...), user_id: str = Depends(get_current_user)):
    data, _ = await read_image_upload(file)
    try:
        detections = await run_in_threadpool(detection_service.detect_ingredients, data, 0.25)
    except RuntimeError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Server-side detection is not available. Detection runs on the device.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    for d in detections:
        d["ingredient_id"] = d.get("ingredient_id") or normalize_ingredient_name(d.get("name", "")) or d.get("name")
    return DetectionResponse(success=True, detections=detections, count=len(detections))


@router.get("/catalog")
def get_catalog():
    return get_catalog_list()


@router.get("/classes")
def get_classes():
    return {"classes": detection_service.CLASS_NAMES, "catalog": get_catalog_list()}
