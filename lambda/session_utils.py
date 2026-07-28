"""
session_utils.py

Shared helper for validating an employee session token against the
Sessions table. Used by any staff-only endpoint (currently just the
dashboard handler, but written generically so more staff-only routes
can reuse it later).
"""

from datetime import datetime


def get_valid_session(sessions_table, token: str):
    """
    Returns the session item if the token exists and hasn't expired,
    otherwise returns None.
    """
    if not token:
        return None

    resp = sessions_table.get_item(Key={"token": token})
    session = resp.get("Item")
    if not session:
        return None

    expires_at = datetime.fromisoformat(session["expires_at"])
    if datetime.utcnow() > expires_at:
        return None

    return session


def extract_bearer_token(event) -> str:
    """
    Pulls the token out of the Authorization header, tolerating both
    a raw token and a "Bearer <token>" style header.
    """
    headers = event.get("headers") or {}
    # API Gateway lower-cases header names inconsistently depending on
    # the source (console test vs real HTTP client), so check both.
    auth_header = headers.get("Authorization") or headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return auth_header.strip()
