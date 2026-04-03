import base64

import pytest
from cryptography.exceptions import InvalidTag

from app.services.encryption_service import decrypt, encrypt, generate_user_salt


def test_generate_user_salt_is_hex_and_32_bytes():
    salt = generate_user_salt()
    assert len(salt) == 64
    int(salt, 16)  # valid hex


def test_encrypt_decrypt_roundtrip():
    salt = generate_user_salt()
    plaintext = "sensitive memory payload"

    encrypted = encrypt(plaintext, salt)
    decoded = base64.b64decode(encrypted.encode("ascii"))

    # nonce (12 bytes) + ciphertext/tag
    assert len(decoded) > 12
    assert decrypt(encrypted, salt) == plaintext


def test_decrypt_with_wrong_salt_raises():
    encrypted = encrypt("hello", generate_user_salt())

    with pytest.raises(InvalidTag):
        decrypt(encrypted, generate_user_salt())
