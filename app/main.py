from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.db import create_mongo_client
from app.core.health import router as health_router
from app.core.metrics import setup_metrics
from app.core.redis import create_redis
from app.modules import MODULE_ROUTERS


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    mongo = create_mongo_client(settings.mongodb_uri)
    redis = create_redis(settings.redis_url)
    app.state.mongo = mongo
    app.state.db = mongo[settings.mongodb_db]
    app.state.redis = redis
    try:
        yield
    finally:
        await redis.aclose()
        await mongo.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router)
    for router in MODULE_ROUTERS:
        app.include_router(router)
    setup_metrics(app)
    return app


app = create_app()
