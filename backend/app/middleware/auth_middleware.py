"""
Authentication dependencies for PantryPilot AI.

Every private route depends on `get_current_user`, which returns the verified
user id taken from the JWT `sub` claim. Routes must never accept a user id from
the request body or query string.
"""

from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..database.connection import get_database
from ..services.auth_service import AuthConfigError, decode_token, get_user_by_id, sanitize_user

security = HTTPBearer(auto_error=False)

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers=_UNAUTHORIZED)


def get_current_user_doc(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
    database=Depends(get_database),
) -> Dict[str, Any]:
    """Validate the bearer token and return the raw user document."""
    if creds is None or not creds.credentials:
        raise _unauthorized("Not authenticated. Please sign in.")
    try:
        payload = decode_token(creds.credentials.strip())
    except AuthConfigError:
        raise HTTPException(status_code=503, detail="Authentication is not configured on the server.")
    if not payload:
        raise _unauthorized("Your session has expired. Please sign in again.")

    user = get_user_by_id(database, str(payload["sub"]))
    if not user:
        raise _unauthorized("Account not found. Please sign in again.")
    if int(payload.get("tv", 0)) != int(user.get("token_version", 0) or 0):
        raise _unauthorized("Your session is no longer valid. Please sign in again.")
    return user


def get_current_user(user: Dict[str, Any] = Depends(get_current_user_doc)) -> str:
    """Return the authenticated user's id as a string."""
    return str(user["_id"])


def get_current_user_profile(user: Dict[str, Any] = Depends(get_current_user_doc)) -> Dict[str, Any]:
    return sanitize_user(user)
