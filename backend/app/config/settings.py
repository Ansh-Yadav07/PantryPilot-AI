"""
Application settings, loaded from environment variables (and backend/.env for
local development). Production secrets must be supplied by the hosting
provider's environment-variable settings, never committed to the repository.
"""

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _BACKEND_DIR / ".env"

# Models verified against the Gemini API model list (Oct 2026). The first one
# that answers wins; overloaded (503) or rate-limited (429) models fall through.
DEFAULT_GEMINI_MODELS = "gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH) if _ENV_PATH.exists() else None,
        extra="ignore",
    )

    environment: str = "development"  # development | production | test

    mongodb_uri: str = ""
    database_name: str = "pantrypilot_ai"

    gemini_api_key: str = ""
    gemini_models: str = DEFAULT_GEMINI_MODELS

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_days: int = 7

    # Comma-separated list of browser origins allowed by CORS. Native mobile and
    # desktop apps do not use CORS, so this is only needed for Flutter web.
    cors_origins: str = ""

    max_upload_mb: int = 10

    @field_validator("jwt_secret_key")
    @classmethod
    def _secret_strength(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def gemini_model_list(self) -> List[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
