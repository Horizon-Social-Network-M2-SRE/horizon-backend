"""Access and refresh tokens, grouped in sessions.

- Session: created at login, identified by ``sid``. It survives refresh rotation and
  ends at logout. Redis keeps ``auth:session:<sid>`` -> hash of its current refresh token.
- Access token: short-lived JWT (``sub``, ``sid``, ``jti``, ``iat``, ``exp``, ``type=access``).
  Refused once its session has ended (logout), or through a Redis deny list keyed by ``jti``,
  kept only until the token would have expired anyway.
- Refresh token: opaque random string. Redis stores only its SHA-256 under
  ``auth:refresh:<hash>`` -> ``<user id>:<sid>``, with the refresh TTL. It is
  single-use: refreshing deletes it atomically (GETDEL) and issues a new pair in
  the same session. Logout revokes the session's refresh token through ``sid``,
  so the client does not need to send it.
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
SESSION_PREFIX = "auth:session:"


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    session_id: str
    jti: str
    exp: int


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class RefreshGrant:
    user_id: str
    session_id: str


def create_access_token(user_id: str, session_id: str, settings: Settings, now: float | None = None) -> str:
    issued = int(now if now is not None else time.time())
    claims = {
        "sub": user_id,
        "sid": session_id,
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
            options={"require": ["sub", "sid", "jti", "exp", "iat"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if claims.get("type") != "access":
        raise InvalidTokenError("not an access token")
    return AccessClaims(
        user_id=str(claims["sub"]), session_id=str(claims["sid"]), jti=str(claims["jti"]), exp=int(claims["exp"])
    )


def _hash(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode()).hexdigest()


async def issue_tokens(
    redis: Redis, user_id: str, settings: Settings, session_id: str | None = None
) -> TokenPair:
    """New pair. Without ``session_id`` a new session starts (login); with it, the session continues (refresh)."""
    session_id = session_id or uuid.uuid4().hex
    refresh_token = secrets.token_urlsafe(48)
    digest = _hash(refresh_token)
    ttl = settings.refresh_token_ttl_seconds
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(REFRESH_PREFIX + digest, f"{user_id}:{session_id}", ex=ttl)
        pipe.set(SESSION_PREFIX + session_id, digest, ex=ttl)
        await pipe.execute()
    return TokenPair(
        access_token=create_access_token(user_id, session_id, settings),
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_seconds,
    )


async def consume_refresh_token(redis: Redis, refresh_token: str) -> RefreshGrant | None:
    """Delete the refresh token and return its owner, or None if unknown, expired, used or revoked."""
    value = await redis.getdel(REFRESH_PREFIX + _hash(refresh_token))
    if value is None:
        return None
    user_id, _, session_id = value.partition(":")
    return RefreshGrant(user_id=user_id, session_id=session_id)


async def revoke_session(redis: Redis, session_id: str) -> None:
    """End the session: its current refresh token stops working."""
    digest = await redis.getdel(SESSION_PREFIX + session_id)
    if digest:
        await redis.delete(REFRESH_PREFIX + digest)


async def deny_access_token(redis: Redis, claims: AccessClaims, now: float | None = None) -> None:
    remaining = claims.exp - int(now if now is not None else time.time())
    if remaining > 0:
        await redis.set(DENY_PREFIX + claims.jti, "1", ex=remaining)


async def is_access_token_revoked(redis: Redis, claims: AccessClaims) -> bool:
    """True if the token was signed out, or its session has ended.

    Checking the session covers every access token issued in it (including the ones from
    before the last refresh), not only the one sent with the logout. One round trip.
    """
    async with redis.pipeline(transaction=False) as pipe:
        pipe.exists(DENY_PREFIX + claims.jti)
        pipe.exists(SESSION_PREFIX + claims.session_id)
        denied, session_alive = await pipe.execute()
    return bool(denied) or not session_alive
