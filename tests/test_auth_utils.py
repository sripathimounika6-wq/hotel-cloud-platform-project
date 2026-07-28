"""
Unit tests for auth_utils.py (password hashing/verification).
Run with: python -m pytest tests/ -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from auth_utils import hash_password, verify_password


def test_correct_password_verifies():
    stored = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", stored) is True


def test_incorrect_password_fails():
    stored = hash_password("correct-horse-battery-staple")
    assert verify_password("wrong-password", stored) is False


def test_same_password_different_hashes():
    # Different random salts each time - hashes should not match even
    # for the same input password (confirms salting is actually happening).
    stored1 = hash_password("same-password")
    stored2 = hash_password("same-password")
    assert stored1 != stored2
    assert verify_password("same-password", stored1) is True
    assert verify_password("same-password", stored2) is True


def test_malformed_stored_value_fails_safely():
    assert verify_password("anything", "not-a-valid-hash-format") is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
