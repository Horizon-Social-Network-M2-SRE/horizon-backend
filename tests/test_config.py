import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_jwt_secret_is_required(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None)


def test_short_jwt_secret_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "too-short")
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None)


def test_jwt_secret_read_from_env_and_hidden_in_repr(monkeypatch):
    secret = "s" * 48
    monkeypatch.setenv("JWT_SECRET", secret)
    settings = Settings(_env_file=None)
    assert settings.jwt_secret.get_secret_value() == secret
    assert secret not in repr(settings)
