"""
Authentication service for PantryPilot AI.

Handles password hashing, JWT token creation/verification and user CRUD
operations backed by the MongoDB 'users' collection.

Tokens carry a `tv` (token version) claim. Changing the password bumps the
user's token_version, which invalidates every previously issued token.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from ..config.settings import settings

MIN_PASSWORD_LENGTH = 8


class AuthConfigError(RuntimeError):
    """Raised when JWT signing is not configured."""


def _pw_bytes(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes; truncate explicitly so hashing and
    # verification behave identically (bcrypt>=4.1 raises on longer input).
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(_pw_bytes(plain_password), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def _require_secret() -> str:
    if not settings.jwt_secret_key:
        raise AuthConfigError("JWT_SECRET_KEY is not configured")
    return settings.jwt_secret_key


def create_token(user: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT for a raw or sanitized user document."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=settings.jwt_access_token_expire_days))
    user_id = str(user.get("_id") or user.get("id"))
    payload = {
        "sub": user_id,
        "tv": int(user.get("token_version", 0) or 0),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, _require_secret(), algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Return the payload of a valid, unexpired token, otherwise None."""
    try:
        return jwt.decode(
            token,
            _require_secret(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "iat"]},
        )
    except jwt.PyJWTError:
        return None


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Strip secrets from a user document before returning it to clients."""
    if not user:
        return {}
    return {
        "id": str(user.get("_id", user.get("id", ""))),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "household_size": user.get("household_size"),
        "dietary_preferences": user.get("dietary_preferences", []),
        "currency": user.get("currency", "INR"),
        "created_at": _iso(user.get("created_at")),
        "updated_at": _iso(user.get("updated_at")),
    }


def get_user_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    if db is None or not email:
        return None
    return db["users"].find_one({"email": email.strip().lower()})


def get_user_by_id(db, user_id: str) -> Optional[Dict[str, Any]]:
    if db is None or not user_id or not ObjectId.is_valid(user_id):
        return None
    return db["users"].find_one({"_id": ObjectId(user_id)})


def create_user(db, name: str, email: str, password: str) -> Dict[str, Any]:
    """Create a user and return the raw stored document (with _id)."""
    cleaned_name = name.strip()
    cleaned_email = email.strip().lower()
    if not cleaned_name:
        raise ValueError("Name cannot be empty")
    if not cleaned_email or "@" not in cleaned_email:
        raise ValueError("A valid email address is required")
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")

    if get_user_by_email(db, cleaned_email):
        raise ValueError("An account with this email already exists")

    now = datetime.utcnow()
    user_doc = {
        "name": cleaned_name,
        "email": cleaned_email,
        "password_hash": hash_password(password),
        "token_version": 0,
        "currency": "INR",
        "dietary_preferences": [],
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = db["users"].insert_one(user_doc)
    except DuplicateKeyError:
        # Lost a race with a concurrent registration for the same email.
        raise ValueError("An account with this email already exists")
    user_doc["_id"] = result.inserted_id
    return user_doc


_DUMMY_HASH: Optional[str] = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")
    return _DUMMY_HASH


def authenticate_user(db, email: str, password: str) -> Optional[Dict[str, Any]]:
    """Return the raw user document on success, None otherwise."""
    user = get_user_by_email(db, email)
    if not user:
        # Spend comparable time so response timing doesn't reveal which emails exist.
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.get("password_hash", "")):
        return None
    return user


def update_profile(db, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = {k: v for k, v in updates.items()
               if k in ("name", "household_size", "dietary_preferences", "currency") and v is not None}
    if not allowed:
        return get_user_by_id(db, user_id)
    allowed["updated_at"] = datetime.utcnow()
    db["users"].update_one({"_id": ObjectId(user_id)}, {"$set": allowed})
    return get_user_by_id(db, user_id)


def change_password(db, user_id: str, current_password: str, new_password: str) -> Dict[str, Any]:
    user = get_user_by_id(db, user_id)
    if not user or not verify_password(current_password, user.get("password_hash", "")):
        raise PermissionError("Current password is incorrect")
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    db["users"].update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password_hash": hash_password(new_password), "updated_at": datetime.utcnow()},
            "$inc": {"token_version": 1},
        },
    )
    return get_user_by_id(db, user_id)


USER_COLLECTIONS = ("pantry_items", "expenses", "shopping_items", "meal_plans", "idempotency_keys")


def delete_account(db, user_id: str, password: str) -> None:
    """Permanently delete a user and every record they own."""
    user = get_user_by_id(db, user_id)
    if not user or not verify_password(password, user.get("password_hash", "")):
        raise PermissionError("Password is incorrect")
    for name in USER_COLLECTIONS:
        db[name].delete_many({"user_id": user_id})
    db["users"].delete_one({"_id": user["_id"]})


def ensure_indexes(db) -> None:
    db["users"].create_index("email", unique=True)


class AuthService:
    """Namespace mirroring the module-level functions."""
    hash_password = staticmethod(hash_password)
    verify_password = staticmethod(verify_password)
    create_token = staticmethod(create_token)
    decode_token = staticmethod(decode_token)
    sanitize_user = staticmethod(sanitize_user)
    get_user_by_email = staticmethod(get_user_by_email)
    get_user_by_id = staticmethod(get_user_by_id)
    create_user = staticmethod(create_user)
    authenticate_user = staticmethod(authenticate_user)
    update_profile = staticmethod(update_profile)
    change_password = staticmethod(change_password)
    delete_account = staticmethod(delete_account)
    ensure_indexes = staticmethod(ensure_indexes)
