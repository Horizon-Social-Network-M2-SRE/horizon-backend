import os
import uuid

import pytest

# Must be set before app.main is imported: the app refuses to start without it.
os.environ.setdefault("JWT_SECRET", "test-only-secret-" + "x" * 40)

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_MONGODB_URI = os.environ.get("TEST_MONGODB_URI", "mongodb://localhost:27017")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
# Set in CI: a missing MongoDB or Redis must fail the run, not silently skip the integration tests.
REQUIRE_SERVICES = os.environ.get("REQUIRE_SERVICES") == "1"


@pytest.fixture
def settings():
    return Settings(
        mongodb_uri=TEST_MONGODB_URI,
        mongodb_db=f"horizon_test_{uuid.uuid4().hex[:12]}",
        redis_url=TEST_REDIS_URL,
        jwt_secret=os.environ["JWT_SECRET"],
        refresh_cookie_path="/auth",  # no /api prefix: tests call the app directly
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    # https so the Secure refresh cookie is stored and sent like in a browser.
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture
def services_client(client):
    """Client whose MongoDB and Redis are reachable; skips the test otherwise (fails with REQUIRE_SERVICES=1)."""
    if client.get("/health/ready").status_code != 200:
        message = "MongoDB or Redis not reachable (set TEST_MONGODB_URI / TEST_REDIS_URL)"
        if REQUIRE_SERVICES:
            pytest.fail(message)
        pytest.skip(message)
    yield client
    client.portal.call(client.app.state.redis.flushdb)
    client.portal.call(client.app.state.mongo.drop_database, client.app.state.db.name)
