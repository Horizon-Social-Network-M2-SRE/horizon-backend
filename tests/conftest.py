import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

TEST_MONGODB_URI = os.environ.get("TEST_MONGODB_URI", "mongodb://localhost:27017")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture
def settings():
    return Settings(
        mongodb_uri=TEST_MONGODB_URI,
        mongodb_db=f"horizon_test_{uuid.uuid4().hex[:12]}",
        redis_url=TEST_REDIS_URL,
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def services_client(client):
    """Client whose MongoDB and Redis are reachable; skips the test otherwise."""
    if client.get("/health/ready").status_code != 200:
        pytest.skip("MongoDB or Redis not reachable (set TEST_MONGODB_URI / TEST_REDIS_URL)")
    yield client
    client.portal.call(client.app.state.redis.flushdb)
    client.portal.call(client.app.state.mongo.drop_database, client.app.state.db.name)
