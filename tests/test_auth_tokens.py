import time

import jwt
import pytest

from app.auth.tokens import InvalidTokenError, create_access_token, decode_access_token
from app.core.config import Settings

SETTINGS = Settings(jwt_secret="test-secret-" + "x" * 40)


def test_access_token_roundtrip_and_15_min_lifetime():
    now = time.time()
    claims = decode_access_token(create_access_token("u1", "s1", SETTINGS, now=now), SETTINGS)
    assert claims.user_id == "u1"
    assert claims.session_id == "s1"
    assert claims.exp == int(now) + 15 * 60
    assert len(claims.jti) == 32


def test_each_token_has_a_unique_jti():
    a = decode_access_token(create_access_token("u1", "s1", SETTINGS), SETTINGS)
    b = decode_access_token(create_access_token("u1", "s1", SETTINGS), SETTINGS)
    assert a.jti != b.jti


def test_expired_token_rejected():
    token = create_access_token("u1", "s1", SETTINGS, now=time.time() - 16 * 60)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SETTINGS)


def test_wrong_secret_rejected():
    token = create_access_token("u1", "s1", Settings(jwt_secret="other-secret-" + "y" * 40))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SETTINGS)


@pytest.mark.parametrize("claims", [{"type": "refresh"}, {"type": None}])
def test_non_access_token_rejected(claims):
    now = int(time.time())
    token = jwt.encode(
        {"sub": "u1", "sid": "s1", "jti": "j", "iat": now, "exp": now + 60, **claims}, SETTINGS.jwt_secret.get_secret_value(), algorithm="HS256"
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SETTINGS)


def test_alg_none_rejected():
    now = int(time.time())
    token = jwt.encode({"sub": "u1", "sid": "s1", "jti": "j", "iat": now, "exp": now + 60, "type": "access"}, None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SETTINGS)


def test_garbage_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.jwt", SETTINGS)


def test_token_without_session_id_rejected():
    now = int(time.time())
    token = jwt.encode(
        {"sub": "u1", "jti": "j", "iat": now, "exp": now + 60, "type": "access"},
        SETTINGS.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SETTINGS)
