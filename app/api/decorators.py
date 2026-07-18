from functools import wraps

from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import User


def get_current_api_user():
    """Call after @jwt_required() — returns the User for the current token."""
    user_id = get_jwt_identity()
    return db.session.get(User, int(user_id)) if user_id else None


def api_role_required(*roles):
    """Like the web app's role_required, but for JWT-authenticated API routes."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get("role") not in roles:
                return jsonify(error="Forbidden — this account type can't access this endpoint."), 403
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def error_response(message, status=400):
    return jsonify(error=message), status
