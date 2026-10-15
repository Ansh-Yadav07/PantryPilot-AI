"""
Authentication routes.

- POST  /api/auth/register         create an account, returns a JWT
- POST  /api/auth/login            exchange email + password for a JWT
- GET   /api/auth/me               current user's profile
- PATCH /api/auth/me               update profile fields
- POST  /api/auth/change-password  change password (invalidates old tokens)
- POST  /api/auth/delete-account   delete the account and all its data
- POST  /api/auth/logout           stateless acknowledgement
"""

import re
import threading
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from ..database.connection import get_database
from ..middleware.auth_middleware import get_current_user, get_current_user_doc
from ..services import auth_service
from ..services.auth_service import MIN_PASSWORD_LENGTH, sanitize_user

router = APIRouter()

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")


def _clean_email(v: str) -> str:
    cleaned = (v or "").strip().lower()
    if not EMAIL_REGEX.match(cleaned):
        raise ValueError("Please enter a valid email address")
    return cleaned


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _clean_email(v)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip()


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _clean_email(v)


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    household_size: Optional[int] = Field(None, ge=1, le=20)
    dietary_preferences: Optional[List[str]] = Field(None, max_length=10)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip() if v else v


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=128)


class DeleteAccountRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


class AuthSuccessResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


# ── Simple in-process brute-force throttle for login ──────────────────────
_ATTEMPT_WINDOW_S = 15 * 60
_MAX_ATTEMPTS = 10
_failed_attempts: Dict[str, Deque[float]] = defaultdict(deque)
_attempts_lock = threading.Lock()


def _throttle_key(request: Request, email: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}|{email}"


def _check_throttle(key: str) -> None:
    now = time.monotonic()
    with _attempts_lock:
        q = _failed_attempts[key]
        while q and now - q[0] > _ATTEMPT_WINDOW_S:
            q.popleft()
        if len(q) >= _MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed sign-in attempts. Please wait a few minutes and try again.",
            )


def _record_failure(key: str) -> None:
    with _attempts_lock:
        _failed_attempts[key].append(time.monotonic())


def _clear_failures(key: str) -> None:
    with _attempts_lock:
        _failed_attempts.pop(key, None)


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthSuccessResponse)
def register(payload: RegisterRequest, database=Depends(get_database)):
    try:
        user = auth_service.create_user(database, payload.name, payload.email, payload.password)
    except ValueError as ve:
        code = status.HTTP_409_CONFLICT if "already exists" in str(ve) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(ve))
    return {"access_token": auth_service.create_token(user), "token_type": "bearer", "user": sanitize_user(user)}


@router.post("/login", response_model=AuthSuccessResponse)
def login(payload: LoginRequest, request: Request, database=Depends(get_database)):
    key = _throttle_key(request, payload.email)
    _check_throttle(key)
    user = auth_service.authenticate_user(database, payload.email, payload.password)
    if not user:
        _record_failure(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    _clear_failures(key)
    return {"access_token": auth_service.create_token(user), "token_type": "bearer", "user": sanitize_user(user)}


@router.get("/me")
def get_me(user: Dict[str, Any] = Depends(get_current_user_doc)):
    return {"user": sanitize_user(user)}


@router.patch("/me")
def update_me(payload: ProfileUpdateRequest, user_id: str = Depends(get_current_user), database=Depends(get_database)):
    updated = auth_service.update_profile(database, user_id, payload.model_dump(exclude_none=True))
    return {"user": sanitize_user(updated)}


@router.post("/change-password", response_model=AuthSuccessResponse)
def change_password(payload: ChangePasswordRequest, user_id: str = Depends(get_current_user), database=Depends(get_database)):
    try:
        user = auth_service.change_password(database, user_id, payload.current_password, payload.new_password)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    # Old tokens are now invalid; hand back a fresh one so this device stays signed in.
    return {"access_token": auth_service.create_token(user), "token_type": "bearer", "user": sanitize_user(user)}


@router.post("/delete-account")
def delete_account(payload: DeleteAccountRequest, user_id: str = Depends(get_current_user), database=Depends(get_database)):
    """Permanently delete the account and all of its data (password required)."""
    try:
        auth_service.delete_account(database, user_id, payload.password)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(pe))
    return {"success": True}


@router.post("/logout")
def logout():
    """JWTs are stateless; the client discards its token."""
    return {"success": True}
