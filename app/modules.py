"""Registry of feature modules. Each module owns its router under /<module>."""

from app.auth.router import router as auth_router
from app.connections.router import router as connections_router
from app.feed.router import router as feed_router
from app.interactions.router import router as interactions_router
from app.posts.router import router as posts_router
from app.users.router import router as users_router

MODULE_ROUTERS = [
    auth_router,
    users_router,
    connections_router,
    posts_router,
    feed_router,
    interactions_router,
]
