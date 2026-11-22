from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from app.auth.deps import CurrentUser
from app.auth.security import verify_password
from app.auth.tokens import (
    TokenPair,
    consume_refresh_token,
    deny_access_token,
    issue_tokens,
    revoke_refresh_token,
)
from app.core.db import get_db
from app.core.redis import get_redis

router = APIRouter(prefix="/auth", tags=["auth"])

USERS = "users"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")

    @classmethod
    def from_pair(cls, pair: TokenPair) -> "TokenResponse":
        return cls(access_token=pair.access_token, refresh_token=pair.refresh_token, expires_in=pair.expires_in)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=256)


class Me(BaseModel):
    id: str


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncDatabase, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    """OAuth2 password flow: ``username`` is the email."""
    user = await db[USERS].find_one({"email": form.username.strip().lower()}, {"passwordHash": 1})
    if not verify_password(form.password, user.get("passwordHash") if user else None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    pair = await issue_tokens(redis, str(user["_id"]), request.app.state.settings)
    return TokenResponse.from_pair(pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    body: RefreshRequest,
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    """Exchange a refresh token for a new pair. The old refresh token stops working (rotation)."""
    user_id = await consume_refresh_token(redis, body.refresh_token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    pair = await issue_tokens(redis, user_id, request.app.state.settings)
    return TokenResponse.from_pair(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    claims: CurrentUser,
    redis: Annotated[Redis, Depends(get_redis)],
    body: LogoutRequest | None = None,
) -> Response:
    """Deny the current access token until it expires and delete the given refresh token."""
    if body and body.refresh_token:
        await revoke_refresh_token(redis, body.refresh_token, claims.user_id)
    await deny_access_token(redis, claims)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=Me)
async def me(claims: CurrentUser) -> Me:
    return Me(id=claims.user_id)
