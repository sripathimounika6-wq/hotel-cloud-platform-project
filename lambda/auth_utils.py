"""
auth_utils.py

Small helper module for password hashing, shared by the register and
login Lambda handlers. Uses PBKDF2-HMAC-SHA256 (stdlib hashlib, no
external dependency needed in the Lambda package) with a random
per-user salt.
"""

import hashlib
import hmac
import os
import binascii

PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """
    Returns a string of the form "<salt_hex>$<hash_hex>" so both the
    salt and derived key can be stored together in a single attribute.
    """
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{binascii.hexlify(salt).decode()}${binascii.hexlify(derived).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Recomputes the hash with the stored salt and compares in constant time."""
    try:
        salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    salt = binascii.unhexlify(salt_hex)
    expected = binascii.unhexlify(hash_hex)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(derived, expected)
