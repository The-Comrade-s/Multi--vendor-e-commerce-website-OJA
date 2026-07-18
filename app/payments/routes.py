from flask import Blueprint, redirect, url_for, flash, request, render_template
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Order, Payment
from app.services import payments as gw
from app.services.notifications import notify
from app.services.email import send_order_confirmation_email

payments_bp = Blueprint("payments", __name__)


@payments_bp.route("/pay/<order_number>")
@login_required
def pay(order_number):
    """Entry point after checkout: decides demo vs. real gateway payment."""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    if order.user_id != current_user.id:
        return redirect(url_for("main.home"))

    if order.payment_status == "paid":
        return redirect(url_for("main.order_detail", order_number=order.order_number))

    gateway = request.args.get("gateway", "paystack")

    if not gw.gateway_is_live(gateway):
        # Demo mode — no live keys configured, mark paid instantly so the
        # checkout flow can be fully tested end to end.
        payment = Payment(
            order_id=order.id, gateway="demo", reference=gw.new_reference("DEMO"),
            amount=order.total, status="success",
        )
        db.session.add(payment)
        order.payment_status = "paid"
        db.session.commit()
        flash("Payment successful (demo mode — no live payment gateway configured).", "success")
        notify(order.user_id, "Payment received", f"Order #{order.order_number} is paid.", url_for("main.order_detail", order_number=order.order_number), "bi-credit-card")
        return redirect(url_for("main.order_detail", order_number=order.order_number))

    callback_url = url_for("payments.callback", gateway=gateway, order_number=order.order_number, _external=True)

    if gateway == "paystack":
        result = gw.paystack_initialize(order, current_user.email, callback_url)
    elif gateway == "flutterwave":
        result = gw.flutterwave_initialize(order, current_user.email, callback_url)
    else:
        result = None

    if not result:
        flash("Couldn't start payment with that gateway. Please try again.", "error")
        return redirect(url_for("main.order_detail", order_number=order.order_number))

    payment = Payment(order_id=order.id, gateway=gateway, reference=result["reference"], amount=order.total, status="pending")
    db.session.add(payment)
    db.session.commit()

    return redirect(result["authorization_url"])


@payments_bp.route("/callback/<gateway>/<order_number>")
@login_required
def callback(gateway, order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()

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
        flash("Payment successful!", "success")
        notify(order.user_id, "Payment received", f"Order #{order.order_number} is paid.", url_for("main.order_detail", order_number=order.order_number), "bi-credit-card")
        send_order_confirmation_email(order)
    else:
        order.payment_status = "failed"
        flash("Payment could not be verified. Please try again or choose another method.", "error")

    db.session.commit()
    return redirect(url_for("main.order_detail", order_number=order.order_number))


@payments_bp.route("/receipt/<order_number>")
@login_required
def receipt(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    if order.user_id != current_user.id and not current_user.is_admin:
        return redirect(url_for("main.home"))
    return render_template("main/receipt.html", order=order)
