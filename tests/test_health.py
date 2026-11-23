import pytest


class _Down:
    async def command(self, *_):
        raise ConnectionError("mongo down")

    async def ping(self):
        raise ConnectionError("redis down")


def test_health_does_not_need_services(client):
    client.app.state.db = _Down()
    client.app.state.redis = _Down()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("broken", ["db", "redis"])
def test_ready_returns_503_when_a_dependency_is_down(client, broken):
    setattr(client.app.state, broken, _Down())
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["mongodb" if broken == "db" else "redis"] == "down"


def test_failed_readiness_check_is_logged(client, caplog):
    client.app.state.redis = _Down()
    with caplog.at_level("WARNING", logger="app.core.health"):
        client.get("/health/ready")
    assert "readiness check failed for redis" in caplog.text
    assert "redis down" in caplog.text


def test_ready_with_real_services(services_client):
    response = services_client.get("/health/ready")
    assert response.json() == {"status": "ok", "checks": {"mongodb": "ok", "redis": "ok"}}


def test_mongo_and_redis_round_trip(services_client):
    state = services_client.app.state
    portal = services_client.portal

    portal.call(state.redis.set, "skeleton:check", "1")
    assert portal.call(state.redis.get, "skeleton:check") == "1"

    portal.call(state.db["skeleton_check"].insert_one, {"k": "v"})
    doc = portal.call(state.db["skeleton_check"].find_one, {"k": "v"})
    assert doc["k"] == "v"
