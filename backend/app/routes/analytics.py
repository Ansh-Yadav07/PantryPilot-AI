"""Kitchen analytics computed from the authenticated user's data."""

from fastapi import APIRouter, Depends

from ..database.connection import get_database
from ..middleware.auth_middleware import get_current_user
from ..services.analytics_service import AnalyticsService

router = APIRouter()


@router.get("")
def get_analytics(user_id: str = Depends(get_current_user), database=Depends(get_database)):
    return AnalyticsService.get_analytics(database, user_id=user_id)
