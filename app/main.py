from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.health import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name)
    app.state.settings = settings
    app.include_router(health_router)
    return app


app = create_app()
