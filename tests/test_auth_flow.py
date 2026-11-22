import time

import pytest
from bson import ObjectId

from app.auth.router import USERS
from app.auth.security import hash_password
from app.auth.tokens import DENY_PREFIX, create_access_token

EMAIL, PASSWORD = "ada@example.com", "correct horse battery"


@pytest.fixture
def user_id(services_client):
    state = services_client.app.state
    _id = ObjectId()
    services_client.portal.call(
        state.db[USERS].insert_one, {"_id": _id, "email": EMAIL, "passwordHash": hash_password(PASSWORD)}
    )
    return str(_id)


def _login(client, username=EMAIL, password=PASSWORD):
    return client.post("/auth/login", data={"username": username, "password": password})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- login ----------


def test_login_returns_access_and_refresh_tokens(services_client, user_id):
    response = _login(services_client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["refresh_token"]
    me = services_client.get("/auth/me", headers=_auth(body["access_token"]))
    assert me.json() == {"id": user_id}


def test_login_email_is_case_insensitive(services_client, user_id):
    assert _login(services_client, username="  ADA@Example.com ").status_code == 200


@pytest.mark.parametrize(("username", "password"), [(EMAIL, "wrong"), ("nobody@example.com", PASSWORD)])
def test_login_rejects_bad_credentials_with_same_error(services_client, user_id, username, password):
    response = _login(services_client, username, password)
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect email or password"}


def test_login_requires_form_fields(services_client):
    assert services_client.post("/auth/login", data={"username": EMAIL}).status_code == 422


# ---------- protected routes ----------


def test_me_requires_a_token(services_client):
    assert services_client.get("/auth/me").status_code == 401


def test_expired_access_token_refused(services_client, user_id):
    settings = services_client.app.state.settings
    token = create_access_token(user_id, settings, now=time.time() - settings.access_token_ttl_seconds - 1)
    assert services_client.get("/auth/me", headers=_auth(token)).status_code == 401


def test_tampered_access_token_refused(services_client, user_id):
    token = _login(services_client).json()["access_token"]
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{sig[:-2]}{'AA' if sig[-2:] != 'AA' else 'BB'}"
    assert services_client.get("/auth/me", headers=_auth(tampered)).status_code == 401


# ---------- refresh ----------


def test_refresh_issues_new_pair_and_rotates(services_client, user_id):
    first = _login(services_client).json()
    response = services_client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert services_client.get("/auth/me", headers=_auth(second["access_token"])).json() == {"id": user_id}

    reused = services_client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reused.status_code == 401  # single use


def test_refresh_rejects_unknown_token(services_client):
    assert services_client.post("/auth/refresh", json={"refresh_token": "nope"}).status_code == 401


def test_refresh_token_is_stored_hashed_with_ttl(services_client, user_id):
    tokens = _login(services_client).json()
    redis, portal = services_client.app.state.redis, services_client.portal
    keys = portal.call(redis.keys, "auth:refresh:*")
    assert len(keys) == 1
    assert tokens["refresh_token"] not in keys[0]
    assert 0 < portal.call(redis.ttl, keys[0]) <= 7 * 24 * 3600


# ---------- logout ----------


def test_signed_out_access_token_is_refused(services_client, user_id):
    tokens = _login(services_client).json()
    headers = _auth(tokens["access_token"])
    assert services_client.get("/auth/me", headers=headers).status_code == 200

    response = services_client.post("/auth/logout", headers=headers, json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 204

    assert services_client.get("/auth/me", headers=headers).status_code == 401
    assert services_client.post("/auth/logout", headers=headers).status_code == 401


def test_logout_deletes_refresh_token(services_client, user_id):
    tokens = _login(services_client).json()
    services_client.post(
        "/auth/logout", headers=_auth(tokens["access_token"]), json={"refresh_token": tokens["refresh_token"]}
    )
    response = services_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


def test_deny_list_entry_lives_only_until_token_expiry(services_client, user_id):
    tokens = _login(services_client).json()
    services_client.post("/auth/logout", headers=_auth(tokens["access_token"]))
    redis, portal = services_client.app.state.redis, services_client.portal
    (key,) = portal.call(redis.keys, DENY_PREFIX + "*")
    assert 0 < portal.call(redis.ttl, key) <= 15 * 60


def test_logout_only_signs_out_that_session(services_client, user_id):
    a = _login(services_client).json()
    b = _login(services_client).json()
    services_client.post("/auth/logout", headers=_auth(a["access_token"]), json={"refresh_token": a["refresh_token"]})
    assert services_client.get("/auth/me", headers=_auth(b["access_token"])).status_code == 200
    assert services_client.post("/auth/refresh", json={"refresh_token": b["refresh_token"]}).status_code == 200


def test_logout_cannot_revoke_another_users_refresh_token(services_client, user_id):
    victim = _login(services_client).json()
    other_token = create_access_token(str(ObjectId()), services_client.app.state.settings)
    services_client.post("/auth/logout", headers=_auth(other_token), json={"refresh_token": victim["refresh_token"]})
    assert services_client.post("/auth/refresh", json={"refresh_token": victim["refresh_token"]}).status_code == 200
