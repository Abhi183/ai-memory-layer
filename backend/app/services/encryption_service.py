"""
AES-256-GCM encryption service for memory content.

Each user gets a unique encryption key derived from the server secret + their
personal salt (stored in users.encryption_salt).  Keys are never stored — they
are re-derived on every encrypt/decrypt call, so there is no single key file
to compromise.

Key derivation: PBKDF2-HMAC-SHA256(master_secret, user_salt, iterations=200_000)
Cipher:         AES-256-GCM (authenticated encryption — tamper-evident)
"""

import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from app.config import settings


_BACKEND = default_backend()
_ITERATIONS = 200_000
_KEY_LENGTH = 32  # 256 bits


def _derive_key(salt_hex: str) -> bytes:
    """Derive a 256-bit key from the server secret + user salt."""
    salt = bytes.fromhex(salt_hex)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=salt,
        iterations=_ITERATIONS,
        backend=_BACKEND,
    )
    return kdf.derive(settings.secret_key.encode())


def generate_user_salt() -> str:
    """Generate a unique salt for a new user. Stored in users.encryption_salt."""
    return os.urandom(32).hex()


def encrypt(plaintext: str, user_salt: str) -> str:
    """
    Encrypt plaintext with AES-256-GCM.
    Returns base64-encoded string: nonce(12 bytes) || ciphertext+tag
    """
    key = _derive_key(user_salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # Prepend nonce so we can recover it during decryption
    payload = nonce + ciphertext
    return base64.b64encode(payload).decode("ascii")


def decrypt(encrypted: str, user_salt: str) -> str:
    """
    Decrypt an AES-256-GCM ciphertext produced by encrypt().
    Raises ValueError if the data has been tampered with.
    """
    key = _derive_key(user_salt)
    aesgcm = AESGCM(key)
    payload = base64.b64decode(encrypted.encode("ascii"))
    nonce = payload[:12]
    ciphertext = payload[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
