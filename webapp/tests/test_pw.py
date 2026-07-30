"""Password hashing (real PBKDF2, no mocks)."""

from app.pw import hash_password, verify_password


def test_hash_verify_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert verify_password("s3cret", h)
    assert not verify_password("wrong", h)


def test_hash_is_salted_nondeterministic():
    assert hash_password("x") != hash_password("x")


def test_verify_rejects_garbage_stored():
    assert not verify_password("x", "not-a-valid-hash")
