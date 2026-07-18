from flask import Blueprint, request, jsonify, url_for
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Order, Payment
from app.services import payments as gw
from app.services.notifications import notify
from app.services.email import send_order_confirmation_email
from app.api.decorators import get_current_api_user, error_response
from app.api.serializers import serialize_order_detail

payments_api_bp = Blueprint("payments_api", __name__, url_prefix="/payments")


@payments_api_bp.route("/initiate", methods=["POST"])
@jwt_required()
def initiate():
    """Starts (or short-circuits, in demo mode) payment for an order.

    Returns either {"demo": true, "order": {...}} when paid instantly
    because no gateway keys are configured, or
    {"authorization_url": "...", "reference": "..."} for the client to open
    in an in-app browser / WebView and complete payment.
    """
    user = get_current_api_user()
    data = request.get_json(silent=True) or {}
    order_number = data.get("order_number")
    gateway = data.get("gateway", "paystack")

    order = Order.query.filter_by(order_number=order_number).first()
    if not order or order.user_id != user.id:
        return error_response("Order not found.", 404)
    if order.payment_status == "paid":
        return jsonify(demo=False, already_paid=True, order=serialize_order_detail(order))

    if not gw.gateway_is_live(gateway):
        payment = Payment(order_id=order.id, gateway="demo", reference=gw.new_reference("DEMO"), amount=order.total, status="success")
        db.session.add(payment)
        order.payment_status = "paid"
        db.session.commit()
        notify(user.id, "Payment received", f"Order #{order.order_number} is paid.", f"/orders/{order.order_number}", "bi-credit-card")
        send_order_confirmation_email(order)
        return jsonify(demo=True, order=serialize_order_detail(order))

    # Mobile callback deep-link — the Flutter app should register a matching
    # URL scheme (or use this HTTPS route + intercept the redirect in its
    # WebView) to catch the gateway's redirect after checkout completes.
    callback_url = url_for("payments_api.callback", gateway=gateway, order_number=order.order_number, _external=True)

    if gateway == "paystack":
        result = gw.paystack_initialize(order, user.email, callback_url)
    elif gateway == "flutterwave":
        result = gw.flutterwave_initialize(order, user.email, callback_url)
    else:
        return error_response("Unknown payment gateway.", 400)

    if not result:
        return error_response("Couldn't start payment with that gateway. Please try again.", 502)

    payment = Payment(order_id=order.id, gateway=gateway, reference=result["reference"], amount=order.total, status="pending")
    db.session.add(payment)
    db.session.commit()

    return jsonify(demo=False, authorization_url=result["authorization_url"], reference=result["reference"])


@payments_api_bp.route("/callback/<gateway>/<order_number>", methods=["GET"])
def callback(gateway, order_number):
    """Hit by the payment gateway's redirect after checkout in the WebView.

    Returns a tiny HTML page (not JSON) since this is loaded inside a
    WebView, not called by the app's HTTP client directly. The Flutter app
    should watch for navigation to a URL containing this path and pop the
    WebView, then call GET /orders/<order_number> to refresh state.
    """
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return "Order not found.", 404

    if gateway == "paystack":
        reference = request.args.get("reference")
        success, raw = gw.paystack_verify(reference)
    elif gateway == "flutterwave":
        reference = request.args.get("tx_ref")
        transaction_id = request.args.get("transaction_id")
        success, raw = gw.flutterwave_verify(transaction_id) if transaction_id else (False, {})
    else:
        success, raw, reference = False, {}, None

    payment = Payment.query.filter_by(reference=reference).first() if reference else None
    if payment:
        payment.status = "success" if success else "failed"
        payment.raw_response = str(raw)[:5000]

    if success:
        order.payment_status = "paid"
        notify(order.user_id, "Payment received", f"Order #{order.order_number} is paid.", f"/orders/{order.order_number}", "bi-credit-card")
        send_order_confirmation_email(order)
        message = "Payment successful! You can close this window."
    else:
        order.payment_status = "failed"
        message = "Payment could not be verified. You can close this window and try again."

    db.session.commit()
    return f"<html><body style='font-family:sans-serif;text-align:center;padding:40px;'><h3>{message}</h3></body></html>"


@payments_api_bp.route("/verify/<order_number>", methods=["GET"])
@jwt_required()
def verify(order_number):
    """Polling fallback for the app to check payment status after the
    WebView closes, instead of relying on catching the redirect."""
    user = get_current_api_user()
    order = Order.query.filter_by(order_number=order_number).first()
    if not order or order.user_id != user.id:
        return error_response("Order not found.", 404)
    return jsonify(payment_status=order.payment_status, order=serialize_order_detail(order))
