"""MongoDB connection. One AsyncMongoClient per process, opened in the app lifespan."""

from fastapi import Request
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase


def create_mongo_client(uri: str) -> AsyncMongoClient:
    # The client connects lazily, so the app starts even if MongoDB is not up yet;
    # /health/ready reports it instead.
    return AsyncMongoClient(uri, serverSelectionTimeoutMS=2000, tz_aware=True)


async def ping_mongo(db: AsyncDatabase) -> None:
    await db.command("ping")


def get_db(request: Request) -> AsyncDatabase:
    """FastAPI dependency: the application database."""
    return request.app.state.db
