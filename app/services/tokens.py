"""Time-limited signed tokens for email verification & password reset.

Uses itsdangerous (bundled with Flask) — no database table needed since the
token itself carries the payload and an expiry, verified against SECRET_KEY.
"""
from itsdangerous import URLSafeTimedSerializer
from flask import current_app


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_token(payload: dict, salt: str) -> str:
    return _serializer().dumps(payload, salt=salt)


def verify_token(token: str, salt: str, max_age_seconds: int = 3600):
    """Returns the payload dict, or None if the token is invalid/expired."""
    try:
        return _serializer().loads(token, salt=salt, max_age=max_age_seconds)
    except Exception:
        return None
