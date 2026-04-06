"""
AES-256-GCM encryption service for memory content.

Security model
--------------
Key is derived exclusively from the *user's own passphrase* (Option A — local
CLI) or from a *per-user random secret* stored in the user's DB row (Option B —
server deployments).  There is NO global server secret involved in key
derivation.  This means the server cannot decrypt any user's data: without
the user's passphrase or their individual per-user secret the ciphertext is
opaque, even to a malicious server operator or an attacker who exfiltrates the
database.

Key-derivation paths
--------------------
Option A — argon2id (preferred, local CLI):
    key = argon2id(passphrase, user_salt,
                   time_cost=2, memory_cost=65536, parallelism=1, hash_len=32)

Option B — PBKDF2-HMAC-SHA256 (fallback, server deployments):
    key = PBKDF2(per_user_secret, user_salt, iterations=200_000)
    per_user_secret is a random value stored in the user's own DB row and is
    unique per user; the server cannot derive any other user's key from it
    unless it reads that specific row.

Cipher:   AES-256-GCM (authenticated encryption — tamper-evident)
Storage:  nonce(12 bytes) || ciphertext+GCM-tag — base64-encoded

If neither a passphrase nor a per_user_secret is provided, derive_key() raises
ValueError with a clear message rather than silently falling back to any
global credential.
"""

import os
import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# argon2-cffi low-level API — pip install argon2-cffi
from argon2.low_level import hash_secret_raw, Type


_BACKEND = default_backend()

# PBKDF2 parameters (Option B legacy path)
_PBKDF2_ITERATIONS = 200_000
_KEY_LENGTH = 32  # 256 bits

# argon2id parameters (Option A — OWASP minimum for interactive logins)
_ARGON2_TIME_COST = 2
_ARGON2_MEMORY_COST = 65_536  # 64 MiB
_ARGON2_PARALLELISM = 1
_ARGON2_HASH_LEN = 32


def derive_key(
    user_salt: str,
    *,
    passphrase: str | None = None,
    server_secret: str | None = None,
) -> bytes:
    """
    Derive a 256-bit AES key for the given user.

    Parameters
    ----------
    user_salt:
        Hex-encoded 32-byte random salt stored in users.encryption_salt.
    passphrase:
        Option A (preferred, local CLI).  The user's master passphrase, held
        in memory for the session and sourced from the OS keychain or a
        first-time prompt.  Key is derived via argon2id.
    server_secret:
        Option B (fallback, server deployments).  A random secret that belongs
        exclusively to this user's DB row (users.per_user_secret).  Key is
        derived via PBKDF2-HMAC-SHA256.  Must NOT be a global/shared secret —
        if the same value is used for every user the security model degrades
        back to server-side control.

    Raises
    ------
    ValueError
        When neither passphrase nor server_secret is supplied, or when
        server_secret is empty (which would be indistinguishable from using a
        global blank secret).
    """
    salt = bytes.fromhex(user_salt)

    if passphrase is not None:
        # Option A: argon2id — memory-hard, resistant to GPU/ASIC attacks.
        # The server never sees the passphrase in the clear; it is sourced from
        # the OS keychain on the local machine.
        return hash_secret_raw(
            secret=passphrase.encode("utf-8"),
            salt=salt,
            time_cost=_ARGON2_TIME_COST,
            memory_cost=_ARGON2_MEMORY_COST,
            parallelism=_ARGON2_PARALLELISM,
            hash_len=_ARGON2_HASH_LEN,
            type=Type.ID,
        )

    if server_secret is not None:
        if not server_secret:
            raise ValueError(
                "server_secret must not be empty.  "
                "Pass the user's per-row random secret (users.per_user_secret), "
                "not a blank or shared global value."
            )
        # Option B: PBKDF2 — preserved for backwards compatibility with
        # existing server deployments.  server_secret MUST be the per-user
        # random value from the user's own DB row, not a global env var.
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_LENGTH,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
            backend=_BACKEND,
        )
        return kdf.derive(server_secret.encode("utf-8"))

    raise ValueError(
        "Cannot derive encryption key: neither a passphrase nor a per-user "
        "secret was provided.  "
        "For local CLI use, supply the user's master passphrase (sourced from "
        "the OS keychain via keyring).  "
        "For server deployments, supply the per-user random secret stored in "
        "users.per_user_secret.  "
        "Do NOT pass a global SERVER_SECRET — doing so would allow the server "
        "to decrypt every user's data."
    )


# ---------------------------------------------------------------------------
# Legacy shim: the old internal _derive_key(salt_hex) used settings.secret_key
# as the 'server_secret'.  Code that still calls encrypt()/decrypt() without
# an explicit key source now uses Option B with settings.secret_key as the
# per-user secret IF it is available, printing a deprecation warning.
# New code should pass passphrase= or server_secret= explicitly.
# ---------------------------------------------------------------------------

def _legacy_derive_key(salt_hex: str) -> bytes:
    """
    Backwards-compatible key derivation used by the plain encrypt()/decrypt()
    helpers.  Falls back to settings.secret_key as the per-user secret.

    DEPRECATED: This path uses a global server secret, which means the server
    can decrypt user data.  Migrate callers to pass passphrase= (Option A) or
    per-user server_secret= (Option B) to derive_key() directly.
    """
    import warnings
    from app.config import settings

    warnings.warn(
        "encrypt()/decrypt() are using the global SECRET_KEY for key derivation. "
        "This allows the server to decrypt user data.  "
        "Migrate to derive_key(salt, passphrase=...) or "
        "derive_key(salt, server_secret=user.per_user_secret).",
        DeprecationWarning,
        stacklevel=3,
    )
    return derive_key(salt_hex, server_secret=settings.secret_key)


def generate_user_salt() -> str:
    """Generate a unique 32-byte salt for a new user.  Stored in users.encryption_salt."""
    return os.urandom(32).hex()


def generate_per_user_secret() -> str:
    """
    Generate a unique 32-byte random secret for Option B (server deployments).
    Stored in users.per_user_secret.  Never used as a global/shared value.
    """
    return os.urandom(32).hex()


def encrypt(plaintext: str, user_salt: str, *, passphrase: str | None = None, server_secret: str | None = None) -> str:
    """
    Encrypt *plaintext* with AES-256-GCM.

    Returns a base64-encoded payload: nonce(12 bytes) || ciphertext+GCM-tag.

    If neither passphrase nor server_secret is supplied the function falls back
    to the legacy path (global SECRET_KEY) and emits a DeprecationWarning.
    Pass passphrase= for the local CLI path or server_secret= for the server
    deployment path.
    """
    if passphrase is not None or server_secret is not None:
        key = derive_key(user_salt, passphrase=passphrase, server_secret=server_secret)
    else:
        key = _legacy_derive_key(user_salt)

    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = nonce + ciphertext
    return base64.b64encode(payload).decode("ascii")


def decrypt(encrypted: str, user_salt: str, *, passphrase: str | None = None, server_secret: str | None = None) -> str:
    """
    Decrypt an AES-256-GCM ciphertext produced by encrypt().

    Raises ValueError if the ciphertext has been tampered with (GCM tag
    verification fails).

    If neither passphrase nor server_secret is supplied the function falls back
    to the legacy path (global SECRET_KEY) and emits a DeprecationWarning.
    """
    if passphrase is not None or server_secret is not None:
        key = derive_key(user_salt, passphrase=passphrase, server_secret=server_secret)
    else:
        key = _legacy_derive_key(user_salt)

    aesgcm = AESGCM(key)
    payload = base64.b64decode(encrypted.encode("ascii"))
    nonce = payload[:12]
    ciphertext = payload[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
