from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, limiter
from app.models import User, VendorProfile
from app.utils import slugify, EMAIL_VERIFY_SALT, PASSWORD_RESET_SALT
from app.services.tokens import generate_token, verify_token
from app.services.email import send_verification_email, send_password_reset_email

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "customer")
        store_name = request.form.get("store_name", "").strip()

        if role not in ("customer", "vendor"):
            role = "customer"

        if not name or not email or not password:
            flash("Please fill in all required fields.", "error")
            return render_template("auth/register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
            return render_template("auth/register.html")

        if role == "vendor" and not store_name:
            flash("Please provide a store name to register as a vendor.", "error")
            return render_template("auth/register.html")

        user = User(name=name, email=email, phone=phone, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # get user.id before commit

        if role == "vendor":
            base_slug = slugify(store_name)
            slug = base_slug
            counter = 1
            while VendorProfile.query.filter_by(store_slug=slug).first():
                counter += 1
                slug = f"{base_slug}-{counter}"
            profile = VendorProfile(user_id=user.id, store_name=store_name, store_slug=slug, status="pending")
            db.session.add(profile)

        db.session.commit()

        token = generate_token({"user_id": user.id}, EMAIL_VERIFY_SALT)
        send_verification_email(user, token)

        login_user(user)
        flash("Account created! Check your email to verify your address (or continue exploring right away).", "success")

        if role == "vendor":
            return redirect(url_for("vendor.dashboard"))
        return redirect(url_for("main.home"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            flash("Incorrect email or password.", "error")
            return render_template("auth/login.html")

        if not user.is_active_account:
            flash("This account has been suspended. Contact support for help.", "error")
            return render_template("auth/login.html")

        login_user(user)
        flash(f"Welcome back, {user.name.split(' ')[0]}!", "success")

        if user.is_admin:
            return redirect(url_for("admin.dashboard"))
        if user.is_vendor:
            return redirect(url_for("vendor.dashboard"))
        return redirect(request.args.get("next") or url_for("main.home"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("main.home"))


# ------------------------------------------------------------ Verification

@auth_bp.route("/verify/resend")
@login_required
def resend_verification():
    if current_user.is_email_verified:
        flash("Your email is already verified.", "info")
        return redirect(url_for("main.profile"))
    token = generate_token({"user_id": current_user.id}, EMAIL_VERIFY_SALT)
    send_verification_email(current_user, token)
    flash("Verification email sent — check your inbox.", "success")
    return redirect(url_for("main.profile"))


@auth_bp.route("/verify/<token>")
def verify_email(token):
    data = verify_token(token, EMAIL_VERIFY_SALT, max_age_seconds=3600)
    if not data:
        flash("That verification link is invalid or has expired. Request a new one from your profile.", "error")
        return redirect(url_for("auth.login"))

    user = User.query.get(data["user_id"])
    if user:
        user.is_email_verified = True
        db.session.commit()
        flash("Your email has been verified!", "success")
    return redirect(url_for("main.home"))


# --------------------------------------------------------- Password reset

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_token({"user_id": user.id}, PASSWORD_RESET_SALT)
            send_password_reset_email(user, token)
        # Same message whether or not the account exists, to avoid leaking who has an account
        flash("If that email is registered, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    data = verify_token(token, PASSWORD_RESET_SALT, max_age_seconds=3600)
    if not data:
        flash("That reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.get(data["user_id"])
    if not user:
        flash("Account not found.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("auth/reset_password.html", token=token)
        if password != confirm:
            flash("Passwords don't match.", "error")
            return render_template("auth/reset_password.html", token=token)

        user.set_password(password)
        db.session.commit()
        flash("Password updated — you can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)
