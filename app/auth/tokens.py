"""Access and refresh tokens.

- Access token: short-lived JWT (``sub``, ``jti``, ``iat``, ``exp``, ``type=access``).
  Signed-out tokens are refused through a Redis deny list keyed by ``jti``,
  kept only until the token would have expired anyway.
- Refresh token: opaque random string. Redis stores only its SHA-256 under
  ``auth:refresh:<hash>`` -> user id, with the refresh TTL. It is single-use:
  refreshing deletes it atomically (GETDEL) and issues a new pair.
"""

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass

import jwt
from redis.asyncio import Redis

from app.core.config import Settings

DENY_PREFIX = "auth:deny:"
REFRESH_PREFIX = "auth:refresh:"


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    jti: str
    exp: int


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def create_access_token(user_id: str, settings: Settings, now: float | None = None) -> str:
    issued = int(now if now is not None else time.time())
    claims = {
        "sub": user_id,
        "jti": uuid.uuid4().hex,
        "iat": issued,
        "exp": issued + settings.access_token_ttl_seconds,
        "type": "access",
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "jti", "exp", "iat"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if claims.get("type") != "access":
        raise InvalidTokenError("not an access token")
    return AccessClaims(user_id=str(claims["sub"]), jti=str(claims["jti"]), exp=int(claims["exp"]))


def _refresh_key(refresh_token: str) -> str:
    return REFRESH_PREFIX + hashlib.sha256(refresh_token.encode()).hexdigest()


async def issue_tokens(redis: Redis, user_id: str, settings: Settings) -> TokenPair:
    refresh_token = secrets.token_urlsafe(48)
    await redis.set(_refresh_key(refresh_token), user_id, ex=settings.refresh_token_ttl_seconds)
    return TokenPair(
        access_token=create_access_token(user_id, settings),
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_seconds,
    )


async def consume_refresh_token(redis: Redis, refresh_token: str) -> str | None:
    """Delete the refresh token and return its user id, or None if unknown/expired/used."""
    return await redis.getdel(_refresh_key(refresh_token))


async def revoke_refresh_token(redis: Redis, refresh_token: str, user_id: str) -> None:
    """Delete the refresh token if it belongs to ``user_id`` (others' tokens are left alone)."""
    key = _refresh_key(refresh_token)
    if await redis.get(key) == user_id:
        await redis.delete(key)


async def deny_access_token(redis: Redis, claims: AccessClaims, now: float | None = None) -> None:
    remaining = claims.exp - int(now if now is not None else time.time())
    if remaining > 0:
        await redis.set(DENY_PREFIX + claims.jti, "1", ex=remaining)


async def is_access_token_denied(redis: Redis, jti: str) -> bool:
    return bool(await redis.exists(DENY_PREFIX + jti))
