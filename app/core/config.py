from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or a local .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Horizon Backend"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "horizon"
    redis_url: str = "redis://localhost:6379/0"

    # Auth. No default on purpose: the repository is public, so a built-in secret would let
    # anyone forge tokens. The app refuses to start without JWT_SECRET (>= 32 chars).
    # Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 7 * 24 * 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
