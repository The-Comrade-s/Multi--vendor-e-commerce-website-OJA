"""Outbound email helper.

If MAIL_USERNAME isn't configured (e.g. local dev, or before you've set up a
mailbox for OJÀ), emails are logged to the console instead of sent, so
verification/reset flows still work end-to-end for testing without crashing.
"""
import logging
from flask import current_app
from flask_mail import Message

from app.extensions import mail

logger = logging.getLogger("oja.email")


def send_email(to: str, subject: str, body: str):
    if not current_app.config.get("MAIL_USERNAME"):
        logger.info("[DEV MODE — email not sent] To: %s | Subject: %s\n%s", to, subject, body)
        return False

    try:
        msg = Message(subject=subject, recipients=[to], body=body)
        mail.send(msg)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)
        return False


def send_verification_email(user, token):
    from flask import url_for

    link = url_for("auth.verify_email", token=token, _external=True)
    send_email(
        to=user.email,
        subject="Verify your OJÀ account",
        body=f"Hi {user.name},\n\nPlease verify your email by clicking the link below:\n{link}\n\n"
        f"This link expires in 1 hour. If you didn't create an OJÀ account, ignore this email.",
    )


def send_password_reset_email(user, token):
    from flask import url_for

    link = url_for("auth.reset_password", token=token, _external=True)
    send_email(
        to=user.email,
        subject="Reset your OJÀ password",
        body=f"Hi {user.name},\n\nSomeone requested a password reset for your OJÀ account.\n"
        f"Click the link below to set a new password:\n{link}\n\n"
        f"This link expires in 1 hour. If you didn't request this, you can ignore this email.",
    )


def send_order_confirmation_email(order):
    send_email(
        to=order.customer.email,
        subject=f"Order confirmed — #{order.order_number}",
        body=f"Hi {order.full_name},\n\nYour order #{order.order_number} has been placed successfully.\n"
        f"Total: \u20A6{float(order.total):,.0f}\n\nWe'll notify you as it's processed and shipped.",
    )
