import time

import pytest
from bson import ObjectId

from app.auth.router import USERS
from app.auth.security import hash_password
from app.auth.tokens import (
    DENY_PREFIX,
    SESSION_PREFIX,
    consume_refresh_token,
    create_access_token,
    revoke_session,
    rotate_tokens,
)

EMAIL, PASSWORD = "ada@example.com", "correct horse battery"
COOKIE = "refresh_token"


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


def _refresh(client, cookie=None):
    """Refresh with the browser's cookie jar, or with an explicit (e.g. stolen or old) cookie."""
    headers = {"Cookie": f"{COOKIE}={cookie}"} if cookie else None
    return client.post("/auth/refresh", headers=headers)


# ---------- login ----------


def test_login_returns_access_token_and_sets_refresh_cookie(services_client, user_id):
    response = _login(services_client)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}  # no refresh token in JS reach
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert response.cookies.get(COOKIE)
    me = services_client.get("/auth/me", headers=_auth(body["access_token"]))
    assert me.json() == {"id": user_id}


def test_refresh_cookie_attributes(services_client, user_id):
    header = _login(services_client).headers["set-cookie"]
    attrs = {a.strip().split("=")[0].lower(): a.strip() for a in header.split(";")}
    assert "httponly" in attrs
    assert "secure" in attrs
    assert attrs["samesite"].lower() == "samesite=strict"
    assert attrs["path"] == "Path=/auth"
    assert attrs["max-age"] == f"Max-Age={7 * 24 * 3600}"


def test_login_email_is_case_insensitive(services_client, user_id):
    assert _login(services_client, username="  ADA@Example.com ").status_code == 200


@pytest.mark.parametrize(("username", "password"), [(EMAIL, "wrong"), ("nobody@example.com", PASSWORD)])
def test_login_rejects_bad_credentials_with_same_error(services_client, user_id, username, password):
    response = _login(services_client, username, password)
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect email or password"}
    assert COOKIE not in response.cookies


def test_login_requires_form_fields(services_client):
    assert services_client.post("/auth/login", data={"username": EMAIL}).status_code == 422


# ---------- protected routes ----------


def test_me_requires_a_token(services_client):
    assert services_client.get("/auth/me").status_code == 401


def test_expired_access_token_refused(services_client, user_id):
    settings = services_client.app.state.settings
    token = create_access_token(user_id, "s1", settings, now=time.time() - settings.access_token_ttl_seconds - 1)
    assert services_client.get("/auth/me", headers=_auth(token)).status_code == 401


def test_tampered_access_token_refused(services_client, user_id):
    token = _login(services_client).json()["access_token"]
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{sig[:-2]}{'AA' if sig[-2:] != 'AA' else 'BB'}"
    assert services_client.get("/auth/me", headers=_auth(tampered)).status_code == 401


# ---------- refresh ----------


def test_refresh_uses_the_cookie_and_rotates_it(services_client, user_id):
    first = _login(services_client)
    old_cookie = first.cookies[COOKIE]

    response = _refresh(services_client)  # browser sends the cookie by itself
    assert response.status_code == 200
    assert response.cookies[COOKIE] != old_cookie
    new_access = response.json()["access_token"]
    assert services_client.get("/auth/me", headers=_auth(new_access)).json() == {"id": user_id}

    assert _refresh(services_client, cookie=old_cookie).status_code == 401  # single use


def test_refresh_without_cookie_rejected(services_client):
    assert services_client.post("/auth/refresh").status_code == 401


def test_refresh_rejects_unknown_or_oversized_cookie(services_client):
    assert _refresh(services_client, cookie="nope").status_code == 401
    assert _refresh(services_client, cookie="x" * 300).status_code == 401


def test_refresh_token_is_stored_hashed_with_ttl(services_client, user_id):
    cookie = _login(services_client).cookies[COOKIE]
    redis, portal = services_client.app.state.redis, services_client.portal
    keys = portal.call(redis.keys, "auth:refresh:*")
    assert len(keys) == 1
    assert cookie not in keys[0]
    assert 0 < portal.call(redis.ttl, keys[0]) <= 7 * 24 * 3600


def test_refresh_keeps_the_session(services_client, user_id):
    _login(services_client)
    _refresh(services_client)
    redis, portal = services_client.app.state.redis, services_client.portal
    assert len(portal.call(redis.keys, SESSION_PREFIX + "*")) == 1
    assert len(portal.call(redis.keys, "auth:refresh:*")) == 1  # the used token is gone


# ---------- logout ----------


def test_signed_out_access_token_is_refused(services_client, user_id):
    access = _login(services_client).json()["access_token"]
    headers = _auth(access)
    assert services_client.get("/auth/me", headers=headers).status_code == 200

    assert services_client.post("/auth/logout", headers=headers).status_code == 204

    assert services_client.get("/auth/me", headers=headers).status_code == 401
    assert services_client.post("/auth/logout", headers=headers).status_code == 204  # idempotent


def test_logout_revokes_refresh_token_and_clears_cookie(services_client, user_id):
    login = _login(services_client)
    cookie = login.cookies[COOKIE]
    response = services_client.post("/auth/logout", headers=_auth(login.json()["access_token"]))
    assert 'refresh_token=""' in response.headers["set-cookie"] or "Max-Age=0" in response.headers["set-cookie"]
    assert COOKIE not in services_client.cookies
    # Even a client that kept a copy of the cookie cannot get a new access token.
    assert _refresh(services_client, cookie=cookie).status_code == 401


def test_logout_after_refresh_revokes_the_rotated_token(services_client, user_id):
    first_access = _login(services_client).json()["access_token"]
    rotated = _refresh(services_client).cookies[COOKIE]
    # Sign out with the *old* access token: same session, so the rotated refresh token dies too.
    services_client.post("/auth/logout", headers=_auth(first_access))
    assert _refresh(services_client, cookie=rotated).status_code == 401


def test_logout_refuses_every_access_token_of_the_session(services_client, user_id):
    before_refresh = _login(services_client).json()["access_token"]
    after_refresh = _refresh(services_client).json()["access_token"]
    assert services_client.post("/auth/logout", headers=_auth(after_refresh)).status_code == 204
    # The token from before the refresh is in the same session, so it is refused too.
    assert services_client.get("/auth/me", headers=_auth(before_refresh)).status_code == 401


def test_logout_with_expired_access_token_uses_the_refresh_cookie(services_client, user_id):
    login = _login(services_client)
    cookie = login.cookies[COOKIE]
    settings = services_client.app.state.settings
    expired = create_access_token(user_id, "any", settings, now=time.time() - settings.access_token_ttl_seconds - 1)

    response = services_client.post("/auth/logout", headers=_auth(expired))  # browser sends the cookie

    assert response.status_code == 204
    assert COOKIE not in services_client.cookies
    assert _refresh(services_client, cookie=cookie).status_code == 401
    assert services_client.get("/auth/me", headers=_auth(login.json()["access_token"])).status_code == 401


def test_logout_without_any_credentials_just_clears_the_cookie(services_client):
    response = services_client.post("/auth/logout")
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"] or 'refresh_token=""' in response.headers["set-cookie"]


def test_deny_list_entry_lives_only_until_token_expiry(services_client, user_id):
    access = _login(services_client).json()["access_token"]
    services_client.post("/auth/logout", headers=_auth(access))
    redis, portal = services_client.app.state.redis, services_client.portal
    (key,) = portal.call(redis.keys, DENY_PREFIX + "*")
    assert 0 < portal.call(redis.ttl, key) <= 15 * 60


def test_logout_only_signs_out_that_session(services_client, user_id):
    a = _login(services_client)
    b = _login(services_client)
    b_cookie = b.cookies[COOKIE]
    services_client.post("/auth/logout", headers=_auth(a.json()["access_token"]))
    assert services_client.get("/auth/me", headers=_auth(b.json()["access_token"])).status_code == 200
    assert _refresh(services_client, cookie=b_cookie).status_code == 200


# ---------- metrics ----------


def _count(client, name, result):
    for line in client.get("/metrics").text.splitlines():
        if line.startswith(f'{name}{{result="{result}"}}'):
            return float(line.split()[-1])
    raise AssertionError(f"{name}{{result={result}}} not exported")


def test_login_and_refresh_are_counted(services_client, user_id):
    before = {
        (n, r): _count(services_client, n, r)
        for n in ("auth_login_total", "auth_refresh_total")
        for r in ("success", "failure")
    }
    _login(services_client)
    _login(services_client, password="wrong")
    _login(services_client, password="wrong")
    _refresh(services_client)
    _refresh(services_client, cookie="nope")

    def delta(n, r):
        return _count(services_client, n, r) - before[(n, r)]

    assert delta("auth_login_total", "success") == 1
    assert delta("auth_login_total", "failure") == 2
    assert delta("auth_refresh_total", "success") == 1
    assert delta("auth_refresh_total", "failure") == 1


def test_refresh_racing_logout_does_not_revive_the_session(services_client, user_id):
    """Refresh consumes its token, logout runs, then refresh tries to store the new pair."""
    cookie = _login(services_client).cookies[COOKIE]
    state, portal = services_client.app.state, services_client.portal

    grant = portal.call(consume_refresh_token, state.redis, cookie)  # refresh, step 1
    portal.call(revoke_session, state.redis, grant.session_id)  # logout in between
    assert portal.call(rotate_tokens, state.redis, grant, state.settings) is None  # refresh, step 2

    assert portal.call(state.redis.keys, "auth:*") == []
