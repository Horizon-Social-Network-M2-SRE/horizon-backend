from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from app.auth.deps import CurrentUser, optional_bearer_token
from app.auth.metrics import LOGINS, REFRESHES
from app.auth.security import verify_password
from app.auth.tokens import (
    InvalidTokenError,
    TokenPair,
    consume_refresh_token,
    decode_access_token,
    deny_access_token,
    issue_tokens,
    revoke_session,
    rotate_tokens,
    session_of_refresh_token,
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
    # Token responses must never be cached by a browser or proxy (RFC 6749, section 5.1).
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
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
    # argon2 is CPU-bound (~50-100 ms): run it in the thread pool so other requests,
    # including health checks, keep being served during a burst of logins.
    password_hash = user.get("passwordHash") if user else None
    if not await run_in_threadpool(verify_password, form.password, password_hash):
        LOGINS.labels("failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = request.app.state.settings
    pair = await issue_tokens(redis, str(user["_id"]), settings)
    LOGINS.labels("success").inc()
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
    pair = await rotate_tokens(redis, grant, settings) if grant else None
    if pair is None:
        REFRESHES.labels("failure").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    REFRESHES.labels("success").inc()
    return _token_response(response, pair, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    token: Annotated[str | None, Depends(optional_bearer_token)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    """End the session: its refresh token stops working and its access tokens are refused.

    The session is found from the access token, or, only when that is missing or no longer
    valid, from the refresh token cookie (a user coming back after 15 minutes can still sign out).
    Always clears the cookie and answers 204, so signing out twice is harmless.
    """
    settings = request.app.state.settings
    claims = None
    if token:
        try:
            claims = decode_access_token(token, settings)
        except InvalidTokenError:
            pass
    if claims is not None:
        await revoke_session(redis, claims.session_id)
        await deny_access_token(redis, claims)
    else:
        cookie = request.cookies.get(settings.refresh_cookie_name)
        session_id = await session_of_refresh_token(redis, cookie) if cookie and len(cookie) <= 256 else None
        if session_id:
            await revoke_session(redis, session_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response, settings)
    return response


@router.get("/me", response_model=Me)
async def me(claims: CurrentUser) -> Me:
    return Me(id=claims.user_id)
