from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt_identity, get_jwt,
)

from app.extensions import db, limiter
from app.models import User, VendorProfile
from app.utils import slugify, EMAIL_VERIFY_SALT, PASSWORD_RESET_SALT
from app.services.tokens import generate_token, verify_token
from app.services.email import send_verification_email, send_password_reset_email
from app.api.decorators import get_current_api_user, error_response
from app.api.serializers import serialize_user

auth_api_bp = Blueprint("auth_api", __name__, url_prefix="/auth")


def _tokens_for(user):
    claims = {"role": user.role}
    return {
        "access_token": create_access_token(identity=str(user.id), additional_claims=claims),
        "refresh_token": create_refresh_token(identity=str(user.id), additional_claims=claims),
        "user": serialize_user(user),
    }


@auth_api_bp.route("/register", methods=["POST"])
@limiter.limit("10 per hour")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    role = data.get("role") if data.get("role") in ("customer", "vendor") else "customer"
    store_name = (data.get("store_name") or "").strip()

    if not name or not email or not password:
        return error_response("name, email, and password are required.")
    if len(password) < 6:
        return error_response("Password must be at least 6 characters.")
    if User.query.filter_by(email=email).first():
        return error_response("An account with that email already exists.", 409)
    if role == "vendor" and not store_name:
        return error_response("store_name is required to register as a vendor.")

    user = User(name=name, email=email, phone=phone, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    if role == "vendor":
        base_slug = slugify(store_name)
        slug, counter = base_slug, 1
        while VendorProfile.query.filter_by(store_slug=slug).first():
            counter += 1
            slug = f"{base_slug}-{counter}"
        db.session.add(VendorProfile(user_id=user.id, store_name=store_name, store_slug=slug, status="pending"))

    db.session.commit()

    token = generate_token({"user_id": user.id}, EMAIL_VERIFY_SALT)
    send_verification_email(user, token)

    return jsonify(_tokens_for(user)), 201


@auth_api_bp.route("/login", methods=["POST"])
@limiter.limit("15 per hour")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if user is None or not user.check_password(password):
        return error_response("Incorrect email or password.", 401)
    if not user.is_active_account:
        return error_response("This account has been suspended.", 403)

    return jsonify(_tokens_for(user)), 200


@auth_api_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user = get_current_api_user()
    if not user:
        return error_response("Account not found.", 404)
    claims = {"role": user.role}
    return jsonify(access_token=create_access_token(identity=str(user.id), additional_claims=claims))


@auth_api_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = get_current_api_user()
    if not user:
        return error_response("Account not found.", 404)
    return jsonify(serialize_user(user))


@auth_api_bp.route("/me", methods=["PATCH"])
@jwt_required()
def update_me():
    user = get_current_api_user()
    if not user:
        return error_response("Account not found.", 404)

    data = request.get_json(silent=True) or {}
    if "name" in data and data["name"].strip():
        user.name = data["name"].strip()
    if "phone" in data:
        user.phone = data["phone"].strip()
    db.session.commit()
    return jsonify(serialize_user(user))


@auth_api_bp.route("/verify/resend", methods=["POST"])
@jwt_required()
def resend_verification():
    user = get_current_api_user()
    if user.is_email_verified:
        return jsonify(message="Already verified."), 200
    token = generate_token({"user_id": user.id}, EMAIL_VERIFY_SALT)
    send_verification_email(user, token)
    return jsonify(message="Verification email sent."), 200


@auth_api_bp.route("/verify/<token>", methods=["POST"])
def verify_email(token):
    data = verify_token(token, EMAIL_VERIFY_SALT, max_age_seconds=3600)
    if not data:
        return error_response("That verification link is invalid or has expired.", 400)
    user = db.session.get(User, data["user_id"])
    if user:
        user.is_email_verified = True
        db.session.commit()
    return jsonify(message="Email verified."), 200


@auth_api_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("10 per hour")
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if user:
        token = generate_token({"user_id": user.id}, PASSWORD_RESET_SALT)
        send_password_reset_email(user, token)
    # Always the same response — avoid leaking which emails have accounts.
    return jsonify(message="If that email is registered, a reset link has been sent."), 200


@auth_api_bp.route("/reset-password/<token>", methods=["POST"])
def reset_password(token):
    data = verify_token(token, PASSWORD_RESET_SALT, max_age_seconds=3600)
    if not data:
        return error_response("That reset link is invalid or has expired.", 400)
    user = db.session.get(User, data["user_id"])
    if not user:
        return error_response("Account not found.", 404)

    body = request.get_json(silent=True) or {}
    password = body.get("password") or ""
    if len(password) < 6:
        return error_response("Password must be at least 6 characters.")

    user.set_password(password)
    db.session.commit()
    return jsonify(message="Password updated."), 200


@auth_api_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    # Stateless JWTs — the app just discards the tokens client-side.
    # Kept as an endpoint for a consistent client API surface (and a place
    # to hook token blocklisting later if that's ever needed).
    return jsonify(message="Logged out."), 200
