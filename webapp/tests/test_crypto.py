"""Token encryption round-trip (real Fernet, no mocks)."""

from app.crypto import decrypt_token, encrypt_token


def test_roundtrip_recovers_plaintext():
    token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    ciphertext = encrypt_token(token)
    assert ciphertext != token.encode()
    assert decrypt_token(ciphertext) == token


def test_ciphertext_is_nondeterministic():
    # Fernet embeds a random IV + timestamp, so two encryptions differ.
    assert encrypt_token("same") != encrypt_token("same")
