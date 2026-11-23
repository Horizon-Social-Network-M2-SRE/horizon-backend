from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis

from app.auth.tokens import AccessClaims, InvalidTokenError, decode_access_token, is_access_token_revoked
from app.core.redis import get_redis

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
# Same scheme, but the token may be missing (logout also works from the refresh cookie).
optional_bearer_token = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_access_claims(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AccessClaims:
    """Valid, unexpired and not signed out. Use as the dependency for protected routes."""
    try:
        claims = decode_access_token(token, request.app.state.settings)
    except InvalidTokenError:
        raise _UNAUTHORIZED
    if await is_access_token_revoked(redis, claims):
        raise _UNAUTHORIZED
    return claims


CurrentUser = Annotated[AccessClaims, Depends(get_access_claims)]
