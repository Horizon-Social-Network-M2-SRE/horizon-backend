from app.auth.security import hash_password, verify_password


def test_hash_is_argon2_and_verifies():
    h = hash_password("s3cret-pass")
    assert h.startswith("$argon2id$")
    assert "s3cret-pass" not in h
    assert verify_password("s3cret-pass", h)


def test_wrong_password_rejected():
    assert not verify_password("nope", hash_password("s3cret-pass"))


def test_missing_or_corrupt_hash_rejected():
    assert not verify_password("not-a-real-password", None)
    assert not verify_password("x", "garbage")
