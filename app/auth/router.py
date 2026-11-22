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
    revoke_session,
)
from app.core.config import Settings
from app.core.db import get_db
from app.core.redis import get_redis

router = APIRouter(prefix="/auth", tags=["auth"])

USERS = "users"


class TokenResponse(BaseModel):
    """The refresh token is never in the body: it travels only in an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


def _token_response(response: Response, pair: TokenPair, settings: Settings) -> TokenResponse:
    response.set_cookie(
        settings.refresh_cookie_name,
        pair.refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        path=settings.refresh_cookie_path,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return TokenResponse(access_token=pair.access_token, expires_in=pair.expires_in)


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )


class Me(BaseModel):
    id: str


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    response: Response,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncDatabase, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    """OAuth2 password flow (``username`` is the email). Sets the refresh token cookie."""
    user = await db[USERS].find_one({"email": form.username.strip().lower()}, {"passwordHash": 1})
    if not verify_password(form.password, user.get("passwordHash") if user else None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = request.app.state.settings
    pair = await issue_tokens(redis, str(user["_id"]), settings)
    return _token_response(response, pair, settings)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    """Exchange the refresh token cookie for a new access token and a new cookie (rotation)."""
    settings = request.app.state.settings
    token = request.cookies.get(settings.refresh_cookie_name)
    grant = await consume_refresh_token(redis, token) if token and len(token) <= 256 else None
    if grant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    pair = await issue_tokens(redis, grant.user_id, settings, session_id=grant.session_id)
    return _token_response(response, pair, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    claims: CurrentUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    """End the session: its refresh token stops working and the access token is denied until it expires."""
    await revoke_session(redis, claims.session_id)
    await deny_access_token(redis, claims)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response, request.app.state.settings)
    return response


@router.get("/me", response_model=Me)
async def me(claims: CurrentUser) -> Me:
    return Me(id=claims.user_id)
