"""Redis connection. One connection pool per process, opened in the app lifespan."""

from fastapi import Request
from redis.asyncio import Redis


def create_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)


async def ping_redis(redis: Redis) -> None:
    await redis.ping()


def get_redis(request: Request) -> Redis:
    """FastAPI dependency: the shared Redis client."""
    return request.app.state.redis
