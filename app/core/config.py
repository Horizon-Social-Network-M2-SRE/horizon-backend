from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or a local .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Horizon Backend"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "horizon"
    redis_url: str = "redis://localhost:6379/0"

    # Auth. JWT_SECRET must be set to a long random value outside local development.
    jwt_secret: str = "dev-only-change-me-0123456789abcdef0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 7 * 24 * 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
