"""Payment gateway integrations.

Both Paystack and Flutterwave are wired to their real REST APIs. If no API
keys are configured (the default, out of the box), OJÀ runs in **demo mode**:
card "payments" are recorded as instantly successful so the full checkout
flow can be tested without a merchant account. Add real keys via environment
variables (see .env.example) once you have a Paystack/Flutterwave account to
go live with actual money movement.
"""
import uuid
import requests
from flask import current_app

PAYSTACK_BASE = "https://api.paystack.co"
FLUTTERWAVE_BASE = "https://api.flutterwave.com/v3"


def gateway_is_live(gateway: str) -> bool:
    if gateway == "paystack":
        return bool(current_app.config.get("PAYSTACK_SECRET_KEY"))
    if gateway == "flutterwave":
        return bool(current_app.config.get("FLUTTERWAVE_SECRET_KEY"))
    return False


def new_reference(prefix="OJA"):
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


# ------------------------------------------------------------- Paystack

def paystack_initialize(order, email, callback_url):
    """Returns dict with 'authorization_url' and 'reference', or None on failure."""
    secret = current_app.config["PAYSTACK_SECRET_KEY"]
    reference = new_reference("PSK")
    try:
        resp = requests.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "email": email,
                "amount": int(float(order.total) * 100),  # kobo
                "reference": reference,
                "callback_url": callback_url,
                "metadata": {"order_number": order.order_number},
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("status"):
            return {"authorization_url": data["data"]["authorization_url"], "reference": reference}
    except requests.RequestException as exc:
        current_app.logger.error("Paystack init failed: %s", exc)
    return None


def paystack_verify(reference):
    """Returns True/False for success, plus the raw response."""
    secret = current_app.config["PAYSTACK_SECRET_KEY"]
    try:
        resp = requests.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=15,
        )
        data = resp.json()
        success = data.get("status") and data["data"]["status"] == "success"
        return success, data
    except requests.RequestException as exc:
        current_app.logger.error("Paystack verify failed: %s", exc)
        return False, {"error": str(exc)}


# ----------------------------------------------------------- Flutterwave

def flutterwave_initialize(order, email, redirect_url):
    secret = current_app.config["FLUTTERWAVE_SECRET_KEY"]
    reference = new_reference("FLW")
    try:
        resp = requests.post(
            f"{FLUTTERWAVE_BASE}/payments",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "tx_ref": reference,
                "amount": str(float(order.total)),
                "currency": "NGN",
                "redirect_url": redirect_url,
                "customer": {"email": email, "name": order.full_name},
                "meta": {"order_number": order.order_number},
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("status") == "success":
            return {"authorization_url": data["data"]["link"], "reference": reference}
    except requests.RequestException as exc:
        current_app.logger.error("Flutterwave init failed: %s", exc)
    return None


def flutterwave_verify(transaction_id):
    secret = current_app.config["FLUTTERWAVE_SECRET_KEY"]
    try:
        resp = requests.get(
            f"{FLUTTERWAVE_BASE}/transactions/{transaction_id}/verify",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=15,
        )
        data = resp.json()
        success = data.get("status") == "success" and data["data"]["status"] == "successful"
        return success, data
    except requests.RequestException as exc:
        current_app.logger.error("Flutterwave verify failed: %s", exc)
        return False, {"error": str(exc)}
