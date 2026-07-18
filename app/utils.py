import re
import uuid
from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def generate_order_number():
    return "ORD-" + uuid.uuid4().hex[:8].upper()


# Salts for the signed tokens used in email verification / password reset.
# Shared between the web auth blueprint and the mobile auth API so both
# issue/verify tokens the same way.
EMAIL_VERIFY_SALT = "email-verify"
PASSWORD_RESET_SALT = "password-reset"


def role_required(*roles):
    """Restrict a route to one or more account roles (e.g. 'vendor', 'admin')."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def vendor_must_be_verified(view_func):
    """Block product publishing etc. until an admin has verified the vendor."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        profile = current_user.vendor_profile
        if not profile or profile.status != "verified":
            flash("Your store is still awaiting admin verification.", "warning")
            return redirect(url_for("vendor.dashboard"))
        return view_func(*args, **kwargs)

    return wrapped
