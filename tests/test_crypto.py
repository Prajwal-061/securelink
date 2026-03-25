import pytest

from src.crypto_vault import decrypt, encrypt, generate_key


def test_encrypt_decrypt_roundtrip() -> None:
    key = generate_key()
    payload = b"secure payload bytes"
    encrypted = encrypt(payload, key)
    decrypted = decrypt(encrypted, key)
    assert decrypted == payload


def test_decrypt_corrupted_payload_raises() -> None:
    key = generate_key()
    payload = b"abc"
    encrypted = encrypt(payload, key)
    corrupted = encrypted[:-1] + (b"0" if encrypted[-1:] != b"0" else b"1")
    with pytest.raises(Exception):
        decrypt(corrupted, key)
