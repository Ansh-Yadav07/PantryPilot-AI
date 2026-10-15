"""AI insights generated from the authenticated user's pantry and expenses."""

from fastapi import APIRouter, Depends

from ..database.connection import get_database
from ..middleware.auth_middleware import get_current_user
from ..services.ai_insight_service import AiInsightService

router = APIRouter()


@router.get("/insights")
def get_ai_insights(user_id: str = Depends(get_current_user), database=Depends(get_database)):
    insights, source = AiInsightService.generate_insights(database, user_id=user_id)
    return {"success": True, "insights": insights, "source": source}
